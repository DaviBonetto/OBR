"""Exportacao deterministica dos rotulos supervisionados para CPU ou Colab."""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class ErroExportacaoTreinamento(RuntimeError):
    """Indica vazamento de divisao ou artefato de treinamento inconsistente."""


@dataclass(frozen=True, slots=True)
class ConfiguracaoExportacaoTreinamento:
    """Fontes locais e destino do pacote transportavel."""

    raiz_brutos: Path
    rotulos_consolidados: Path
    arquivo_saida: Path


def _sha256(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def _adicionar_bytes(arquivo: zipfile.ZipFile, nome: str, conteudo: bytes) -> None:
    info = zipfile.ZipInfo(nome, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    arquivo.writestr(info, conteudo, compresslevel=6)


class ExportadorDatasetTreinamento:
    """Empacota somente treino/validacao com mascara consolidada existente."""

    def __init__(self, configuracao: ConfiguracaoExportacaoTreinamento) -> None:
        self.configuracao = configuracao

    def exportar(self) -> dict[str, object]:
        cfg = self.configuracao
        anotacoes_path = cfg.rotulos_consolidados / "anotacoes.jsonl"
        manifesto_rotulos_path = cfg.rotulos_consolidados / "manifesto.json"
        if cfg.arquivo_saida.exists():
            raise ErroExportacaoTreinamento(f"Arquivo de saida ja existe: {cfg.arquivo_saida}")
        if not anotacoes_path.is_file() or not manifesto_rotulos_path.is_file():
            raise ErroExportacaoTreinamento("Rotulos consolidados incompletos")
        if not cfg.raiz_brutos.is_dir():
            raise ErroExportacaoTreinamento("Raiz de imagens brutas nao encontrada")

        registros_saida: list[str] = []
        arquivos: list[tuple[str, bytes]] = []
        por_divisao = {"treino": 0, "validacao": 0}
        for linha in anotacoes_path.read_text(encoding="utf-8").splitlines():
            if not linha.strip():
                continue
            anotacao = json.loads(linha)
            divisao = str(anotacao["divisao"])
            if divisao not in por_divisao:
                raise ErroExportacaoTreinamento(f"Divisao proibida na exportacao: {divisao}")
            if anotacao["mascara"] is None:
                continue
            origem_relativa = PurePosixPath(str(anotacao["origem"]))
            mascara_relativa = PurePosixPath(str(anotacao["mascara"]))
            imagem_path = cfg.raiz_brutos / Path(*origem_relativa.parts)
            mascara_path = cfg.rotulos_consolidados / Path(*mascara_relativa.parts)
            try:
                imagem = imagem_path.read_bytes()
                mascara = mascara_path.read_bytes()
            except OSError as erro:
                raise ErroExportacaoTreinamento(
                    f"Imagem ou mascara ausente para {anotacao['id_amostra']}"
                ) from erro
            if _sha256(mascara) != anotacao["sha256_mascara"]:
                raise ErroExportacaoTreinamento(
                    f"Hash da mascara divergiu: {anotacao['id_amostra']}"
                )

            imagem_zip = (PurePosixPath("imagens") / origem_relativa).as_posix()
            mascara_zip = (PurePosixPath("rotulos") / mascara_relativa).as_posix()
            arquivos.extend(((imagem_zip, imagem), (mascara_zip, mascara)))
            registro = {
                "versao": 1,
                "id_amostra": anotacao["id_amostra"],
                "divisao": divisao,
                "tipo_quadro": anotacao["tipo_quadro"],
                "trajetoria_desejada": anotacao["trajetoria_desejada"],
                "imagem": imagem_zip,
                "mascara": mascara_zip,
                "sha256_imagem": _sha256(imagem),
                "sha256_mascara": _sha256(mascara),
                "estado_rotulo": anotacao["estado_rotulo"],
            }
            registros_saida.append(json.dumps(registro, ensure_ascii=False, sort_keys=True))
            por_divisao[divisao] += 1

        conteudo_indice = ("\n".join(registros_saida) + "\n").encode()
        manifesto_interno: dict[str, object] = {
            "versao_manifesto": 1,
            "tipo": "dataset_segmentacao_fase3_inicial",
            "divisao_teste_incluida": False,
            "quantidades": {"total": len(registros_saida), **por_divisao},
            "sha256_indice": _sha256(conteudo_indice),
            "sha256_manifesto_rotulos": _sha256(manifesto_rotulos_path.read_bytes()),
            "uso": "treino_inicial_e_active_learning; nao_e_treino_final",
        }
        conteudo_manifesto = (
            json.dumps(manifesto_interno, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode()

        cfg.arquivo_saida.parent.mkdir(parents=True, exist_ok=True)
        temporario = cfg.arquivo_saida.with_suffix(cfg.arquivo_saida.suffix + ".tmp")
        try:
            with zipfile.ZipFile(temporario, "w") as arquivo:
                _adicionar_bytes(arquivo, "indice.jsonl", conteudo_indice)
                _adicionar_bytes(arquivo, "manifesto.json", conteudo_manifesto)
                for nome, conteudo in sorted(arquivos):
                    _adicionar_bytes(arquivo, nome, conteudo)
            temporario.replace(cfg.arquivo_saida)
        except Exception:
            temporario.unlink(missing_ok=True)
            raise

        resultado = {
            **manifesto_interno,
            "arquivo": cfg.arquivo_saida.name,
            "bytes": cfg.arquivo_saida.stat().st_size,
            "sha256_arquivo": _sha256(cfg.arquivo_saida.read_bytes()),
        }
        cfg.arquivo_saida.with_suffix(".manifesto.json").write_text(
            json.dumps(resultado, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return resultado
