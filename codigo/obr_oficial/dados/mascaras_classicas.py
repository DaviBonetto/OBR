"""Geracao auditavel de rotulos candidatos pelo baseline classico."""

from __future__ import annotations

import hashlib
import json
import shutil
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from obr_oficial.nucleo.contratos import EstadoDeteccao
from obr_oficial.percepcao.linha import DetectorClassicoLinha


class ErroGeracaoMascaras(RuntimeError):
    """Indica quebra de isolamento, leitura ou gravacao das candidatas."""


DIVISOES_PERMITIDAS = frozenset({"treino", "validacao"})


@dataclass(frozen=True, slots=True)
class ConfiguracaoGeracaoMascaras:
    """Entradas explicitas do processamento em lote."""

    raiz_brutos: Path
    dataset_processado: Path
    saida: Path
    intervalo_sobreposicao: int = 40

    def __post_init__(self) -> None:
        if self.intervalo_sobreposicao < 1:
            raise ErroGeracaoMascaras("intervalo_sobreposicao deve ser positivo")


def _percentil(valores: list[float], percentual: float) -> float:
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    indice = min(len(ordenados) - 1, round((len(ordenados) - 1) * percentual))
    return ordenados[indice]


def _hash_arquivo(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _ler_imagem(caminho: Path) -> np.ndarray | None:
    """Le imagem sem depender do suporte do OpenCV a caminhos Unicode no Windows."""

    try:
        conteudo = caminho.read_bytes()
    except OSError:
        return None
    return cv2.imdecode(np.frombuffer(conteudo, dtype=np.uint8), cv2.IMREAD_COLOR)


def _gravar_png(caminho: Path, imagem: np.ndarray) -> None:
    """Grava PNG de forma portavel para caminhos com caracteres acentuados."""

    sucesso, codificada = cv2.imencode(".png", imagem)
    if not sucesso:
        raise ErroGeracaoMascaras(f"Falha ao codificar imagem: {caminho}")
    try:
        caminho.write_bytes(codificada.tobytes())
    except OSError as erro:
        raise ErroGeracaoMascaras(f"Falha ao gravar imagem: {caminho}") from erro


class GeradorMascarasClassicas:
    """Executa o detector somente em treino/validacao e preserva o teste lacrado."""

    def __init__(
        self,
        configuracao: ConfiguracaoGeracaoMascaras,
        detector: DetectorClassicoLinha,
        *,
        hash_configuracao_detector: str,
    ) -> None:
        self.configuracao = configuracao
        self.detector = detector
        self.hash_configuracao_detector = hash_configuracao_detector

    def gerar(self) -> dict[str, object]:
        cfg = self.configuracao
        amostras_path = cfg.dataset_processado / "amostras.jsonl"
        if cfg.saida.exists():
            raise ErroGeracaoMascaras(f"Saida ja existe: {cfg.saida}")
        if not amostras_path.is_file():
            raise ErroGeracaoMascaras(f"Amostras nao encontradas: {amostras_path}")
        if not cfg.raiz_brutos.is_dir():
            raise ErroGeracaoMascaras(f"Raiz bruta nao encontrada: {cfg.raiz_brutos}")

        temporaria = cfg.saida.parent / f".{cfg.saida.name}.tmp"
        if temporaria.exists():
            shutil.rmtree(temporaria)
        temporaria.mkdir(parents=True)
        auditoria_path = temporaria / "candidatas.jsonl"

        contagens: Counter[str] = Counter()
        matriz: dict[str, Counter[str]] = defaultdict(Counter)
        latencias: list[float] = []
        acertos_presenca = 0
        total_presenca = 0
        linhas_auditoria: list[str] = []
        indice_por_grupo: Counter[tuple[str, str]] = Counter()
        inicio = perf_counter()

        try:
            with amostras_path.open("r", encoding="utf-8") as arquivo:
                for numero, linha in enumerate(arquivo, start=1):
                    if not linha.strip():
                        continue
                    amostra = json.loads(linha)
                    if not amostra.get("selecionada", False):
                        continue
                    divisao = str(amostra["divisao"])
                    if divisao == "teste":
                        # Garantia central: nenhuma imagem do teste e sequer aberta.
                        continue
                    if divisao not in DIVISOES_PERMITIDAS:
                        raise ErroGeracaoMascaras(
                            f"Divisao inesperada na linha {numero}: {divisao}"
                        )

                    tipo = str(amostra["tipo_quadro"])
                    relativo = Path(str(amostra["origem"]["caminho_relativo_raiz"]))
                    origem = cfg.raiz_brutos / relativo
                    imagem = _ler_imagem(origem)
                    if imagem is None:
                        raise ErroGeracaoMascaras(f"Falha ao ler imagem: {origem}")

                    resultado = self.detector.processar(imagem, id_quadro=len(latencias))
                    latencia = resultado.estimativa.tempos.total_ms
                    latencias.append(latencia)
                    presente_previsto = resultado.estimativa.estado is not EstadoDeteccao.PERDIDA
                    presente_esperado = tipo != "sem_linha"
                    acertos_presenca += int(presente_previsto == presente_esperado)
                    total_presenca += 1
                    classe_prevista = "linha" if presente_previsto else "sem_evidencia"
                    matriz[tipo][classe_prevista] += 1
                    contagens[divisao] += 1
                    contagens[f"{divisao}:{tipo}"] += 1

                    destino_relativo = Path("mascaras") / relativo
                    destino = temporaria / destino_relativo
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    _gravar_png(destino, resultado.mascara)

                    grupo = (divisao, tipo)
                    indice_por_grupo[grupo] += 1
                    sobreposicao_relativa: str | None = None
                    if indice_por_grupo[grupo] % cfg.intervalo_sobreposicao == 1:
                        sobreposicao_relativa = self._gravar_sobreposicao(
                            temporaria,
                            relativo,
                            imagem,
                            resultado.mascara,
                            resultado.estimativa.centro_linha,
                        )

                    registro = {
                        "versao": 1,
                        "id_amostra": amostra["id_amostra"],
                        "divisao": divisao,
                        "tipo_quadro": tipo,
                        "trajetoria_desejada": amostra["trajetoria_desejada"],
                        "origem": relativo.as_posix(),
                        "mascara_candidata": destino_relativo.as_posix(),
                        "sobreposicao": sobreposicao_relativa,
                        "estado": resultado.estimativa.estado.value,
                        "confianca": round(resultado.estimativa.confianca, 6),
                        "area_normalizada": round(resultado.area_normalizada, 6),
                        "altura_normalizada": round(resultado.altura_normalizada, 6),
                        "contato_inferior": round(resultado.contato_inferior, 6),
                        "brilho_linha": (
                            None
                            if resultado.brilho_linha is None
                            else round(resultado.brilho_linha, 4)
                        ),
                        "nitidez_borda": round(resultado.nitidez_borda, 4),
                        "ponto_objetivo": (
                            None
                            if resultado.estimativa.ponto_objetivo is None
                            else {
                                "x": round(resultado.estimativa.ponto_objetivo.x, 6),
                                "y": round(resultado.estimativa.ponto_objetivo.y, 6),
                            }
                        ),
                        "latencia_ms": round(latencia, 4),
                        "revisao": "pendente",
                    }
                    linhas_auditoria.append(
                        json.dumps(registro, ensure_ascii=False, sort_keys=True)
                    )

            auditoria_path.write_text("\n".join(linhas_auditoria) + "\n", encoding="utf-8")
            manifesto: dict[str, object] = {
                "versao_manifesto": 1,
                "tipo": "mascaras_candidatas_baseline_classico",
                "divisoes_processadas": sorted(DIVISOES_PERMITIDAS),
                "divisao_teste_processada": False,
                "rotulos_humanos": False,
                "uso_permitido": "pre_anotacao; exige revisao humana",
                "hash_configuracao_detector": self.hash_configuracao_detector,
                "hash_amostras_dataset": _hash_arquivo(amostras_path),
                "quantidades": {
                    "total": len(latencias),
                    "por_divisao": {
                        chave: contagens[chave] for chave in sorted(DIVISOES_PERMITIDAS)
                    },
                    "por_divisao_tipo": {
                        chave: contagens[chave]
                        for chave in sorted(contagens)
                        if ":" in chave
                    },
                },
                "presenca_de_linha": {
                    "acuracia_indireta": round(acertos_presenca / max(1, total_presenca), 6),
                    "matriz_por_tipo": {
                        tipo: dict(sorted(valores.items()))
                        for tipo, valores in sorted(matriz.items())
                    },
                    "observacao": "metrica por tipo de captura; nao mede qualidade pixel a pixel",
                },
                "latencia_cpu_ms": {
                    "mediana": round(statistics.median(latencias), 4) if latencias else 0.0,
                    "p95": round(_percentil(latencias, 0.95), 4),
                    "maxima": round(max(latencias), 4) if latencias else 0.0,
                },
                "duracao_total_s": round(perf_counter() - inicio, 3),
            }
            (temporaria / "manifesto.json").write_text(
                json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporaria.replace(cfg.saida)
            return manifesto
        except Exception:
            if temporaria.exists():
                shutil.rmtree(temporaria)
            raise

    def _gravar_sobreposicao(
        self,
        raiz_saida: Path,
        relativo: Path,
        imagem: np.ndarray,
        mascara: np.ndarray,
        pontos: tuple[object, ...],
    ) -> str:
        cfg = self.detector.configuracao
        y0 = round(imagem.shape[0] * cfg.roi_y)
        y1 = round(imagem.shape[0] * (cfg.roi_y + cfg.roi_altura))
        roi = cv2.resize(imagem[y0:y1], (cfg.largura, cfg.altura), interpolation=cv2.INTER_AREA)
        visual = roi.copy()
        visual[mascara > 0] = (
            0.55 * visual[mascara > 0] + 0.45 * np.array([255, 220, 0])
        ).astype(np.uint8)
        for ponto in pontos:
            x = round(ponto.x * (cfg.largura - 1))
            y = round(ponto.y * (cfg.altura - 1))
            cv2.circle(visual, (x, y), 3, (0, 0, 255), -1, cv2.LINE_AA)
        destino_relativo = Path("sobreposicoes") / relativo
        destino = raiz_saida / destino_relativo
        destino.parent.mkdir(parents=True, exist_ok=True)
        _gravar_png(destino, visual)
        return destino_relativo.as_posix()
