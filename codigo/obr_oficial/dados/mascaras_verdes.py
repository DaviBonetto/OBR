"""Bootstrap auditavel de mascaras dos marcadores verdes oficiais."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import statistics
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

import cv2
import numpy as np
from numpy.typing import NDArray

from obr_oficial.nucleo.configuracao import carregar_toml, exigir_secao


class ErroMascarasVerdes(RuntimeError):
    """Indica quebra de isolamento, configuracao ou integridade das candidatas."""


DIVISOES_PERMITIDAS = frozenset({"treino", "validacao"})
CATEGORIA_NEGATIVA = "sem_verde_negativo"
CATEGORIA_DUPLA = "dois_antes_180"


@dataclass(frozen=True, slots=True)
class ConfiguracaoMascarasVerdes:
    """Parametros congelados do bootstrap cromatico V1."""

    versao: int
    matiz_minima: int
    matiz_maxima: int
    saturacao_minima: int
    valor_minimo: int
    excesso_verde_minimo: int
    diferenca_verde_vermelho_minima: int
    abertura_px: int
    fechamento_px: int
    area_componente_minima: float
    penalidade_borda: float
    limiar_prioridade: float
    razao_ambiguidade: float
    area_por_marcador_minima: float
    area_por_marcador_maxima: float
    hash_arquivo: str

    def __post_init__(self) -> None:
        if self.versao < 1:
            raise ErroMascarasVerdes("versao deve ser positiva")
        if not 0 <= self.matiz_minima < self.matiz_maxima <= 179:
            raise ErroMascarasVerdes("faixa de matiz invalida")
        if not 0 <= self.saturacao_minima <= 255 or not 0 <= self.valor_minimo <= 255:
            raise ErroMascarasVerdes("limites HSV invalidos")
        if self.abertura_px < 1 or self.fechamento_px < 1:
            raise ErroMascarasVerdes("kernels morfologicos devem ser positivos")
        if self.abertura_px % 2 == 0 or self.fechamento_px % 2 == 0:
            raise ErroMascarasVerdes("kernels morfologicos devem ser impares")
        if not 0.0 < self.area_componente_minima < 0.1:
            raise ErroMascarasVerdes("area minima de componente invalida")
        for nome, valor in (
            ("penalidade_borda", self.penalidade_borda),
            ("limiar_prioridade", self.limiar_prioridade),
            ("razao_ambiguidade", self.razao_ambiguidade),
        ):
            if not 0.0 < valor <= 1.0:
                raise ErroMascarasVerdes(f"{nome} deve estar entre zero e um")
        if not 0.0 < self.area_por_marcador_minima < self.area_por_marcador_maxima < 1.0:
            raise ErroMascarasVerdes("intervalo de area por marcador invalido")


@dataclass(frozen=True, slots=True)
class ComponenteVerde:
    """Componente cromatico candidato e suas medidas auditaveis."""

    rotulo: int
    x: int
    y: int
    largura: int
    altura: int
    area: int
    area_normalizada: float
    retangularidade: float
    proporcao_quadrada: float
    centro_y_normalizado: float
    saturacao_mediana: float
    valor_mediano: float
    excesso_verde_mediano: float
    bordas_tocadas: int
    pontuacao: float

    def publico(self) -> dict[str, int | float]:
        dados = asdict(self)
        dados.pop("rotulo")
        return dados


@dataclass(frozen=True, slots=True)
class ResultadoMascaraVerde:
    """Mascara candidata e diagnostico, sem decisao de movimento."""

    mascara: NDArray[np.uint8]
    componentes: tuple[ComponenteVerde, ...]
    quantidade_esperada: int
    quantidade_encontrada: int
    quantidade_selecionada: int
    area_bruta_normalizada: float
    area_mascara_normalizada: float
    confianca: float
    prioridade: str
    motivos_prioridade: tuple[str, ...]


def carregar_configuracao_mascaras_verdes(caminho: Path) -> ConfiguracaoMascarasVerdes:
    """Carrega o TOML oficial e inclui seu hash no contrato de saida."""

    bruto = caminho.read_bytes()
    dados = carregar_toml(caminho)
    raiz = exigir_secao(dados, "mascaras_verdes")
    cor = exigir_secao(dados, "cor")
    morfologia = exigir_secao(dados, "morfologia")
    confianca = exigir_secao(dados, "confianca")
    try:
        return ConfiguracaoMascarasVerdes(
            versao=int(raiz["versao"]),
            matiz_minima=int(cor["matiz_minima"]),
            matiz_maxima=int(cor["matiz_maxima"]),
            saturacao_minima=int(cor["saturacao_minima"]),
            valor_minimo=int(cor["valor_minimo"]),
            excesso_verde_minimo=int(cor["excesso_verde_minimo"]),
            diferenca_verde_vermelho_minima=int(cor["diferenca_verde_vermelho_minima"]),
            abertura_px=int(morfologia["abertura_px"]),
            fechamento_px=int(morfologia["fechamento_px"]),
            area_componente_minima=float(morfologia["area_componente_minima"]),
            penalidade_borda=float(confianca["penalidade_borda"]),
            limiar_prioridade=float(confianca["limiar_prioridade"]),
            razao_ambiguidade=float(confianca["razao_ambiguidade"]),
            area_por_marcador_minima=float(confianca["area_por_marcador_minima"]),
            area_por_marcador_maxima=float(confianca["area_por_marcador_maxima"]),
            hash_arquivo=hashlib.sha256(bruto).hexdigest(),
        )
    except (KeyError, TypeError, ValueError) as erro:
        if isinstance(erro, ErroMascarasVerdes):
            raise
        raise ErroMascarasVerdes(f"Configuracao de mascaras verdes invalida: {erro}") from erro


class DetectorCromaticoVerde:
    """Produz uma pre-anotacao conservadora; nunca substitui a revisao humana."""

    def __init__(self, configuracao: ConfiguracaoMascarasVerdes) -> None:
        self.configuracao = configuracao

    def processar(
        self,
        imagem: NDArray[np.uint8],
        *,
        categoria: str,
        cruz_mista: bool,
    ) -> ResultadoMascaraVerde:
        if imagem.ndim != 3 or imagem.shape[2] != 3:
            raise ErroMascarasVerdes("imagem BGR invalida")
        esperada = _quantidade_marcadores(categoria, cruz_mista)
        bruta = self._mascara_cromatica(imagem)
        area_bruta = float(np.count_nonzero(bruta) / bruta.size)
        componentes, rotulos = self._componentes(bruta, imagem)

        if esperada == 0:
            return ResultadoMascaraVerde(
                mascara=np.zeros(bruta.shape, dtype=np.uint8),
                componentes=(),
                quantidade_esperada=0,
                quantidade_encontrada=len(componentes),
                quantidade_selecionada=0,
                area_bruta_normalizada=area_bruta,
                area_mascara_normalizada=0.0,
                confianca=1.0,
                prioridade="contrato",
                motivos_prioridade=("mascara_vazia_por_contrato",),
            )

        ordenados = _ordenar_componentes(componentes, esperada)
        selecionados = tuple(ordenados[:esperada])
        mascara = np.zeros(bruta.shape, dtype=np.uint8)
        for componente in selecionados:
            _preencher_silhueta_convexa(mascara, rotulos, componente.rotulo)
        area_mascara = float(np.count_nonzero(mascara) / mascara.size)
        confianca, motivos = self._avaliar(
            selecionados,
            ordenados,
            esperada,
            area_mascara,
        )
        return ResultadoMascaraVerde(
            mascara=mascara,
            componentes=selecionados,
            quantidade_esperada=esperada,
            quantidade_encontrada=len(componentes),
            quantidade_selecionada=len(selecionados),
            area_bruta_normalizada=area_bruta,
            area_mascara_normalizada=area_mascara,
            confianca=confianca,
            prioridade="prioritaria" if motivos else "normal",
            motivos_prioridade=tuple(motivos),
        )

    def _mascara_cromatica(self, imagem: NDArray[np.uint8]) -> NDArray[np.uint8]:
        cfg = self.configuracao
        hsv = cv2.cvtColor(imagem, cv2.COLOR_BGR2HSV)
        matiz, saturacao, valor = cv2.split(hsv)
        azul, verde, vermelho = cv2.split(imagem.astype(np.int16))
        excesso_verde = 2 * verde - vermelho - azul
        candidata = (
            (matiz >= cfg.matiz_minima)
            & (matiz <= cfg.matiz_maxima)
            & (saturacao >= cfg.saturacao_minima)
            & (valor >= cfg.valor_minimo)
            & (excesso_verde >= cfg.excesso_verde_minimo)
            & (verde >= vermelho + cfg.diferenca_verde_vermelho_minima)
        )
        mascara = candidata.astype(np.uint8) * 255
        abertura = np.ones((cfg.abertura_px, cfg.abertura_px), dtype=np.uint8)
        fechamento = np.ones((cfg.fechamento_px, cfg.fechamento_px), dtype=np.uint8)
        mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, abertura)
        return cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, fechamento)

    def _componentes(
        self,
        mascara: NDArray[np.uint8],
        imagem: NDArray[np.uint8],
    ) -> tuple[list[ComponenteVerde], NDArray[np.int32]]:
        quantidade, rotulos, estatisticas, _ = cv2.connectedComponentsWithStats(mascara)
        altura_imagem, largura_imagem = mascara.shape
        area_imagem = float(mascara.size)
        hsv = cv2.cvtColor(imagem, cv2.COLOR_BGR2HSV)
        saturacao = hsv[..., 1]
        valor = hsv[..., 2]
        azul, verde, vermelho = cv2.split(imagem.astype(np.int16))
        excesso_verde = 2 * verde - vermelho - azul
        componentes: list[ComponenteVerde] = []
        for rotulo in range(1, quantidade):
            x, y, largura, altura, area = (int(valor) for valor in estatisticas[rotulo])
            area_normalizada = area / area_imagem
            if area_normalizada < self.configuracao.area_componente_minima:
                continue
            retangularidade = area / max(1, largura * altura)
            proporcao_quadrada = min(largura, altura) / max(largura, altura)
            bordas = sum(
                (
                    x == 0,
                    y == 0,
                    x + largura >= largura_imagem,
                    y + altura >= altura_imagem,
                )
            )
            pixels = rotulos == rotulo
            saturacao_mediana = float(np.median(saturacao[pixels]))
            valor_mediano = float(np.median(valor[pixels]))
            excesso_verde_mediano = float(np.median(excesso_verde[pixels]))
            pureza_cor = 0.25 + 0.75 * saturacao_mediana / 255.0
            evidencia_luminosa = 0.20 + 0.80 * valor_mediano / 255.0
            pontuacao = (
                area_normalizada
                * (0.35 + 0.65 * retangularidade)
                * (0.55 + 0.45 * proporcao_quadrada)
                * pureza_cor
                * evidencia_luminosa
                * self.configuracao.penalidade_borda**bordas
            )
            componentes.append(
                ComponenteVerde(
                    rotulo=rotulo,
                    x=x,
                    y=y,
                    largura=largura,
                    altura=altura,
                    area=area,
                    area_normalizada=round(area_normalizada, 8),
                    retangularidade=round(retangularidade, 6),
                    proporcao_quadrada=round(proporcao_quadrada, 6),
                    centro_y_normalizado=round((y + altura / 2.0) / altura_imagem, 6),
                    saturacao_mediana=round(saturacao_mediana, 3),
                    valor_mediano=round(valor_mediano, 3),
                    excesso_verde_mediano=round(excesso_verde_mediano, 3),
                    bordas_tocadas=bordas,
                    pontuacao=round(pontuacao, 8),
                )
            )
        return componentes, rotulos

    def _avaliar(
        self,
        selecionados: tuple[ComponenteVerde, ...],
        todos: list[ComponenteVerde],
        esperada: int,
        area_total: float,
    ) -> tuple[float, list[str]]:
        cfg = self.configuracao
        motivos: list[str] = []
        if len(selecionados) < esperada:
            motivos.append("componentes_insuficientes")
        if selecionados and any(item.bordas_tocadas >= 2 for item in selecionados):
            motivos.append("marcador_parcial_na_borda")
        if selecionados and any(item.retangularidade < 0.45 for item in selecionados):
            motivos.append("forma_irregular")
        area_minima = cfg.area_por_marcador_minima * esperada
        area_maxima = cfg.area_por_marcador_maxima * esperada
        if not area_minima <= area_total <= area_maxima:
            motivos.append("area_fora_da_faixa")
        if len(todos) > esperada and selecionados:
            limite = selecionados[-1].pontuacao * cfg.razao_ambiguidade
            if todos[esperada].pontuacao >= limite:
                motivos.append("componente_extra_ambiguo")

        if not selecionados:
            confianca = 0.0
        else:
            forma = statistics.fmean(
                0.5 * item.retangularidade + 0.5 * item.proporcao_quadrada for item in selecionados
            )
            contagem = min(1.0, len(selecionados) / esperada)
            borda = statistics.fmean(
                self.configuracao.penalidade_borda**item.bordas_tocadas for item in selecionados
            )
            confianca = max(0.0, min(1.0, forma * contagem * borda))
        if confianca < cfg.limiar_prioridade:
            motivos.append("confianca_baixa")
        return round(confianca, 6), sorted(set(motivos))


@dataclass(frozen=True, slots=True)
class ConfiguracaoGeracaoMascarasVerdes:
    """Entradas explicitas do processamento em lote."""

    raiz_brutos: Path
    dataset_curado: Path
    saida: Path


class GeradorMascarasVerdes:
    """Gera candidatas somente em treino/validacao e mantem o teste fechado."""

    def __init__(
        self,
        configuracao: ConfiguracaoGeracaoMascarasVerdes,
        detector: DetectorCromaticoVerde,
    ) -> None:
        self.configuracao = configuracao
        self.detector = detector

    def gerar(self) -> dict[str, Any]:
        cfg = self.configuracao
        indice = cfg.dataset_curado / "amostras.jsonl"
        if cfg.saida.exists():
            raise ErroMascarasVerdes(f"Saida ja existe: {cfg.saida}")
        if not indice.is_file() or not cfg.raiz_brutos.is_dir():
            raise ErroMascarasVerdes("dataset curado ou raiz bruta ausente")
        temporaria = cfg.saida.with_name(f".{cfg.saida.name}.tmp-{uuid4().hex[:8]}")
        temporaria.mkdir(parents=True, exist_ok=False)
        inicio = perf_counter()
        contagens: Counter[str] = Counter()
        latencias: list[float] = []
        registros: list[dict[str, Any]] = []
        try:
            for numero, linha in enumerate(indice.read_text(encoding="utf-8").splitlines(), 1):
                if not linha.strip():
                    continue
                amostra = json.loads(linha)
                divisao = str(amostra["divisao"])
                if divisao == "teste":
                    continue
                if divisao not in DIVISOES_PERMITIDAS:
                    raise ErroMascarasVerdes(f"Divisao inesperada na linha {numero}")
                origem_relativa = Path(str(amostra["origem"]["caminho_relativo_raiz"]))
                origem = cfg.raiz_brutos / origem_relativa
                conteudo = origem.read_bytes()
                if hashlib.sha256(conteudo).hexdigest() != amostra["origem"]["sha256"]:
                    raise ErroMascarasVerdes(f"Hash divergente: {amostra['id_amostra']}")
                imagem = cv2.imdecode(np.frombuffer(conteudo, np.uint8), cv2.IMREAD_COLOR)
                if imagem is None:
                    raise ErroMascarasVerdes(f"Imagem ilegivel: {origem}")
                contexto = amostra["contexto_efetivo"]
                instante = perf_counter()
                resultado = self.detector.processar(
                    imagem,
                    categoria=str(contexto["categoria_verde"]),
                    cruz_mista=bool(contexto["cruz_mista"]),
                )
                latencia = (perf_counter() - instante) * 1_000.0
                latencias.append(latencia)
                destino_relativo = Path("mascaras") / origem_relativa
                destino = temporaria / destino_relativo
                destino.parent.mkdir(parents=True, exist_ok=True)
                _gravar_png(destino, resultado.mascara)
                inicial = (
                    "aprovada_vazia_por_contrato"
                    if contexto["categoria_verde"] == CATEGORIA_NEGATIVA
                    else "pendente"
                )
                registro = {
                    "versao": 1,
                    "id_amostra": amostra["id_amostra"],
                    "divisao": divisao,
                    "categoria_verde": contexto["categoria_verde"],
                    "cruz_mista": contexto["cruz_mista"],
                    "decisao_verde_esperada": contexto["decisao_verde_esperada"],
                    "origem": origem_relativa.as_posix(),
                    "sha256_origem": amostra["origem"]["sha256"],
                    "mascara_candidata": destino_relativo.as_posix(),
                    "sha256_mascara": hashlib.sha256(destino.read_bytes()).hexdigest(),
                    "quantidade_marcadores_esperada": resultado.quantidade_esperada,
                    "quantidade_componentes_encontrada": resultado.quantidade_encontrada,
                    "quantidade_componentes_selecionada": resultado.quantidade_selecionada,
                    "area_bruta_normalizada": round(resultado.area_bruta_normalizada, 8),
                    "area_mascara_normalizada": round(resultado.area_mascara_normalizada, 8),
                    "componentes": [item.publico() for item in resultado.componentes],
                    "confianca_bootstrap": resultado.confianca,
                    "prioridade": resultado.prioridade,
                    "motivos_prioridade": list(resultado.motivos_prioridade),
                    "revisao_inicial": inicial,
                    "rotulo_humano": False,
                }
                registros.append(registro)
                contagens["total"] += 1
                contagens[f"divisao:{divisao}"] += 1
                contagens[f"categoria:{contexto['categoria_verde']}"] += 1
                contagens[f"prioridade:{resultado.prioridade}"] += 1

            quantidade_fila = _marcar_fila_revisao_essencial(registros)
            contagens["fila_revisao_essencial"] = quantidade_fila
            caminho_candidatas = temporaria / "candidatas.jsonl"
            caminho_candidatas.write_text(
                "\n".join(
                    json.dumps(registro, ensure_ascii=False, sort_keys=True)
                    for registro in registros
                )
                + "\n",
                encoding="utf-8",
            )
            manifesto = {
                "versao_manifesto": 1,
                "tipo": "mascaras_verdes_candidatas_cromaticas_v1",
                "divisoes_processadas": sorted(DIVISOES_PERMITIDAS),
                "divisao_teste_processada": False,
                "rotulos_humanos": False,
                "uso_permitido": "pre_anotacao; exige revisao humana antes do treino",
                "hash_configuracao": self.detector.configuracao.hash_arquivo,
                "hash_implementacao": _hash_arquivo(Path(__file__)),
                "hash_indice_curado": _hash_arquivo(indice),
                "hash_candidatas": _hash_arquivo(caminho_candidatas),
                "versoes_execucao": {
                    "opencv": cv2.__version__,
                    "numpy": np.__version__,
                },
                "quantidades": dict(sorted(contagens.items())),
                "latencia_cpu_ms": {
                    "mediana": round(statistics.median(latencias), 4),
                    "p95": round(_percentil(latencias, 0.95), 4),
                    "maxima": round(max(latencias), 4),
                },
                "duracao_total_s": round(perf_counter() - inicio, 3),
                "pronto_para_revisao": True,
                "pronto_para_treinamento": False,
            }
            (temporaria / "manifesto.json").write_text(
                json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporaria.replace(cfg.saida)
            return manifesto
        except Exception:
            shutil.rmtree(temporaria, ignore_errors=True)
            raise


def _quantidade_marcadores(categoria: str, cruz_mista: bool) -> int:
    if categoria == CATEGORIA_NEGATIVA:
        if cruz_mista:
            raise ErroMascarasVerdes("negativo nao pode ser cruz mista")
        return 0
    quantidade = 2 if categoria == CATEGORIA_DUPLA else 1
    return quantidade + int(cruz_mista)


def _ordenar_componentes(
    componentes: list[ComponenteVerde],
    quantidade_esperada: int,
) -> list[ComponenteVerde]:
    """Suprime uma copia refletida abaixo quando existe um unico marcador fisico esperado."""

    ordenados = sorted(componentes, key=lambda item: item.pontuacao, reverse=True)
    if quantidade_esperada != 1 or len(ordenados) < 2:
        return ordenados
    melhor = ordenados[0]
    superiores_plausiveis = [
        item
        for item in ordenados[1:]
        if item.centro_y_normalizado + 0.20 < melhor.centro_y_normalizado
        and item.area_normalizada >= max(0.01, 0.45 * melhor.area_normalizada)
        and item.pontuacao >= 0.45 * melhor.pontuacao
        and item.valor_mediano >= 0.80 * melhor.valor_mediano
    ]
    if not superiores_plausiveis:
        return ordenados
    fisico = max(superiores_plausiveis, key=lambda item: item.pontuacao)
    return [fisico, *(item for item in ordenados if item is not fisico)]


def _gravar_png(caminho: Path, imagem: NDArray[np.uint8]) -> None:
    sucesso, codificada = cv2.imencode(".png", imagem)
    if not sucesso:
        raise ErroMascarasVerdes(f"Falha ao codificar mascara: {caminho}")
    caminho.write_bytes(codificada.tobytes())


def _preencher_silhueta_convexa(
    destino: NDArray[np.uint8],
    rotulos: NDArray[np.int32],
    rotulo: int,
) -> None:
    """Preenche brilhos e sombras internos sem extrapolar o casco dos pixels observados."""

    componente = np.where(rotulos == rotulo, 255, 0).astype(np.uint8)
    contornos, _ = cv2.findContours(componente, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contornos:
        return
    pontos = np.concatenate(contornos, axis=0)
    casco = cv2.convexHull(pontos)
    cv2.fillConvexPoly(destino, casco, 255, lineType=cv2.LINE_8)


def _marcar_fila_revisao_essencial(registros: list[dict[str, Any]]) -> int:
    """Escolhe um representante por sequencia prioritaria sem aprovar seus vizinhos."""

    grupos: list[list[dict[str, Any]]] = []
    grupo_atual: list[dict[str, Any]] = []
    chave_anterior: tuple[Any, ...] | None = None
    quadro_anterior: int | None = None
    for registro in registros:
        registro["fila_revisao_essencial"] = False
        registro["grupo_revisao"] = None
        if registro["prioridade"] != "prioritaria":
            continue
        sessao, quadro = _sessao_e_quadro(str(registro["origem"]))
        chave = (
            sessao,
            str(registro["categoria_verde"]),
            bool(registro["cruz_mista"]),
            tuple(registro["motivos_prioridade"]),
        )
        if (
            grupo_atual
            and chave == chave_anterior
            and quadro_anterior is not None
            and quadro - quadro_anterior <= 10
        ):
            grupo_atual.append(registro)
        else:
            if grupo_atual:
                grupos.append(grupo_atual)
            grupo_atual = [registro]
        chave_anterior = chave
        quadro_anterior = quadro
    if grupo_atual:
        grupos.append(grupo_atual)

    for numero, grupo in enumerate(grupos, 1):
        identificador = f"verde-prioridade-{numero:04d}"
        for registro in grupo:
            registro["grupo_revisao"] = identificador
        representante = min(
            grupo,
            key=lambda item: (float(item["confianca_bootstrap"]), str(item["id_amostra"])),
        )
        representante["fila_revisao_essencial"] = True
    return len(grupos)


def _sessao_e_quadro(origem: str) -> tuple[str, int]:
    caminho = Path(origem)
    sessao = caminho.parts[0] if caminho.parts else origem
    correspondencia = re.search(r"(\d+)$", caminho.stem)
    if correspondencia is None:
        raise ErroMascarasVerdes(f"Numero do quadro ausente na origem: {origem}")
    return sessao, int(correspondencia.group(1))


def _hash_arquivo(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _percentil(valores: list[float], percentual: float) -> float:
    ordenados = sorted(valores)
    indice = min(len(ordenados) - 1, round((len(ordenados) - 1) * percentual))
    return ordenados[indice]
