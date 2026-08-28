"""Pipeline PyTorch da segmentacao neural da linha."""

from __future__ import annotations

import hashlib
import json
import random
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import cv2
import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision.models import MobileNet_V3_Large_Weights
from torchvision.models.segmentation import lraspp_mobilenet_v3_large


class ErroTreinamentoSegmentacao(RuntimeError):
    """Indica dataset, configuracao ou execucao neural invalida."""


@dataclass(frozen=True, slots=True)
class ConfiguracaoTreinamento:
    """Hiperparametros registrados em cada experimento."""

    largura: int
    altura: int
    roi_y: float
    epocas: int
    lote: int
    taxa_aprendizado: float
    decaimento_peso: float
    paciencia: int
    trabalhadores: int
    semente: int
    limiar: float
    peso_bce: float
    peso_dice: float
    aumentos_fortes: bool
    peso_presenca: float = 0.0
    peso_negativo_presenca: float = 1.0
    fracao_topk_presenca: float = 0.01
    area_minima_negativo: float = 0.0
    peso_fpr_selecao: float = 0.0
    peso_amostra_negativa: float = 1.0


def carregar_configuracao_treinamento(caminho: Path) -> ConfiguracaoTreinamento:
    """Carrega o TOML versionado da Fase 3."""

    with caminho.open("rb") as arquivo:
        dados = tomllib.load(arquivo)
    entrada = dados["entrada"]
    treino = dados["treinamento"]
    perda = dados["perda"]
    return ConfiguracaoTreinamento(
        largura=int(entrada["largura"]),
        altura=int(entrada["altura"]),
        roi_y=float(entrada["roi_y"]),
        epocas=int(treino["epocas"]),
        lote=int(treino["lote"]),
        taxa_aprendizado=float(treino["taxa_aprendizado"]),
        decaimento_peso=float(treino["decaimento_peso"]),
        paciencia=int(treino["paciencia"]),
        trabalhadores=int(treino["trabalhadores"]),
        semente=int(treino["semente"]),
        limiar=float(treino["limiar"]),
        peso_bce=float(perda["peso_bce"]),
        peso_dice=float(perda["peso_dice"]),
        aumentos_fortes=bool(treino["aumentos_fortes"]),
        peso_presenca=float(perda.get("peso_presenca", 0.0)),
        peso_negativo_presenca=float(perda.get("peso_negativo_presenca", 1.0)),
        fracao_topk_presenca=float(perda.get("fracao_topk_presenca", 0.01)),
        area_minima_negativo=float(treino.get("area_minima_negativo", 0.0)),
        peso_fpr_selecao=float(treino.get("peso_fpr_selecao", 0.0)),
        peso_amostra_negativa=float(treino.get("peso_amostra_negativa", 1.0)),
    )


def _ler_imagem(caminho: Path, modo: int) -> np.ndarray:
    try:
        conteudo = caminho.read_bytes()
    except OSError as erro:
        raise ErroTreinamentoSegmentacao(f"Arquivo ausente: {caminho}") from erro
    imagem = cv2.imdecode(np.frombuffer(conteudo, dtype=np.uint8), modo)
    if imagem is None:
        raise ErroTreinamentoSegmentacao(f"Imagem invalida: {caminho}")
    return imagem


def carregar_indice_dataset(raiz: Path, divisao: str) -> list[dict[str, Any]]:
    """Le uma divisao permitida e recusa qualquer indice de teste."""

    if divisao not in {"treino", "validacao"}:
        raise ErroTreinamentoSegmentacao(f"Divisao proibida no treinamento: {divisao}")
    caminho = raiz / "indice.jsonl"
    amostras = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if not linha.strip():
            continue
        item = json.loads(linha)
        if item["divisao"] == "teste":
            raise ErroTreinamentoSegmentacao("Indice contaminado pela divisao de teste")
        if item["divisao"] == divisao:
            amostras.append(item)
    if not amostras:
        raise ErroTreinamentoSegmentacao(f"Divisao vazia: {divisao}")
    return amostras


class AumentadorRobusto:
    """Aumentos conjuntos e fotometricos voltados a luz, sombra e reflexo."""

    def __init__(self, forte: bool = True) -> None:
        self.forte = forte

    def __call__(self, imagem: np.ndarray, mascara: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        altura, largura = mascara.shape
        if np.random.random() < 0.5:
            imagem = cv2.flip(imagem, 1)
            mascara = cv2.flip(mascara, 1)
        if np.random.random() < 0.65:
            angulo = float(np.random.uniform(-7.0, 7.0))
            escala = float(np.random.uniform(0.94, 1.06))
            centro = (largura / 2.0, altura / 2.0)
            matriz = cv2.getRotationMatrix2D(centro, angulo, escala)
            matriz[:, 2] += np.random.uniform(-0.04, 0.04, size=2) * [largura, altura]
            imagem = cv2.warpAffine(
                imagem,
                matriz,
                (largura, altura),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REFLECT_101,
            )
            mascara = cv2.warpAffine(
                mascara,
                matriz,
                (largura, altura),
                flags=cv2.INTER_NEAREST,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=0,
            )

        imagem_float = imagem.astype(np.float32) / 255.0
        amplitude = 1.0 if self.forte else 0.55
        gamma = float(np.random.uniform(0.35, 2.15) ** amplitude)
        imagem_float = np.power(np.clip(imagem_float, 0.0, 1.0), gamma)
        ganho = float(np.random.uniform(0.45, 1.65) ** amplitude)
        desvio = float(np.random.uniform(-0.18, 0.18) * amplitude)
        imagem_float = imagem_float * ganho + desvio
        canais = np.random.uniform(0.78, 1.22, size=(1, 1, 3)).astype(np.float32)
        imagem_float *= 1.0 + (canais - 1.0) * amplitude

        if np.random.random() < 0.55:
            pontos = np.array(
                [
                    [np.random.randint(0, largura), 0],
                    [np.random.randint(0, largura), 0],
                    [np.random.randint(0, largura), altura - 1],
                    [np.random.randint(0, largura), altura - 1],
                ],
                dtype=np.int32,
            )
            sombra = np.ones((altura, largura), dtype=np.float32)
            cv2.fillPoly(sombra, [pontos], float(np.random.uniform(0.20, 0.72)))
            sombra = cv2.GaussianBlur(sombra, (0, 0), sigmaX=13, sigmaY=13)
            imagem_float *= sombra[:, :, None]

        if np.random.random() < 0.35:
            brilho = np.zeros((altura, largura), dtype=np.float32)
            centro = (np.random.randint(0, largura), np.random.randint(0, altura))
            eixos = (np.random.randint(12, 70), np.random.randint(8, 45))
            cv2.ellipse(brilho, centro, eixos, 0, 0, 360, 1.0, -1)
            brilho = cv2.GaussianBlur(brilho, (0, 0), sigmaX=15, sigmaY=15)
            imagem_float += brilho[:, :, None] * np.random.uniform(0.15, 0.65)

        if np.random.random() < 0.35:
            sigma = float(np.random.uniform(0.005, 0.045))
            imagem_float += np.random.normal(0.0, sigma, imagem_float.shape).astype(np.float32)
        imagem = np.clip(imagem_float * 255.0, 0, 255).astype(np.uint8)
        if np.random.random() < 0.25:
            imagem = cv2.GaussianBlur(imagem, (3, 3), 0)
        return np.ascontiguousarray(imagem), np.ascontiguousarray(mascara)


class DatasetSegmentacaoLinha(Dataset):
    """Dataset map-style compativel com CPU, Windows e Colab."""

    def __init__(
        self,
        raiz: Path,
        configuracao: ConfiguracaoTreinamento,
        divisao: str,
    ) -> None:
        self.raiz = raiz
        self.configuracao = configuracao
        self.divisao = divisao
        self.amostras = carregar_indice_dataset(raiz, divisao)
        self.aumentador = (
            AumentadorRobusto(configuracao.aumentos_fortes) if divisao == "treino" else None
        )

    def __len__(self) -> int:
        return len(self.amostras)

    def __getitem__(self, indice: int) -> tuple[torch.Tensor, torch.Tensor]:
        item = self.amostras[indice]
        imagem = _ler_imagem(self.raiz / item["imagem"], cv2.IMREAD_COLOR)
        mascara = _ler_imagem(self.raiz / item["mascara"], cv2.IMREAD_GRAYSCALE)
        y0 = round(imagem.shape[0] * self.configuracao.roi_y)
        imagem = imagem[y0:]
        tamanho = (self.configuracao.largura, self.configuracao.altura)
        imagem = cv2.resize(imagem, tamanho, interpolation=cv2.INTER_AREA)
        mascara = cv2.resize(mascara, tamanho, interpolation=cv2.INTER_NEAREST)
        if self.aumentador is not None:
            imagem, mascara = self.aumentador(imagem, mascara)
        imagem = cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        imagem = (imagem - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array(
            [0.229, 0.224, 0.225], dtype=np.float32
        )
        mascara = (mascara >= 128).astype(np.float32)
        tensor_imagem = torch.from_numpy(np.transpose(imagem, (2, 0, 1))).float()
        tensor_mascara = torch.from_numpy(mascara[None]).float()
        return tensor_imagem, tensor_mascara


class SegmentadorLRASPP(nn.Module):
    """LR-ASPP MobileNetV3 com uma unica saida logit para linha."""

    def __init__(self, *, pretreinado: bool = True) -> None:
        super().__init__()
        pesos_backbone = MobileNet_V3_Large_Weights.DEFAULT if pretreinado else None
        self.rede = lraspp_mobilenet_v3_large(
            weights=None,
            weights_backbone=pesos_backbone,
            num_classes=1,
        )

    def forward(self, entrada: torch.Tensor) -> torch.Tensor:
        return self.rede(entrada)["out"]


class _ConvBnAtivacao(nn.Sequential):
    def __init__(
        self,
        entrada: int,
        saida: int,
        *,
        kernel: int = 3,
        passo: int = 1,
        grupos: int = 1,
    ) -> None:
        super().__init__(
            nn.Conv2d(
                entrada,
                saida,
                kernel,
                stride=passo,
                padding=kernel // 2,
                groups=grupos,
                bias=False,
            ),
            nn.BatchNorm2d(saida),
            nn.Hardswish(inplace=True),
        )


class _BlocoSeparavel(nn.Sequential):
    def __init__(self, entrada: int, saida: int, *, passo: int = 1) -> None:
        super().__init__(
            _ConvBnAtivacao(entrada, entrada, passo=passo, grupos=entrada),
            _ConvBnAtivacao(entrada, saida, kernel=1),
        )


class LinhaNet(nn.Module):
    """Encoder-decoder separavel pequeno para comparar com LR-ASPP no Raspberry."""

    def __init__(self) -> None:
        super().__init__()
        self.e1 = _ConvBnAtivacao(3, 16, passo=2)
        self.e2 = nn.Sequential(_BlocoSeparavel(16, 24, passo=2), _BlocoSeparavel(24, 24))
        self.e3 = nn.Sequential(_BlocoSeparavel(24, 40, passo=2), _BlocoSeparavel(40, 40))
        self.e4 = nn.Sequential(_BlocoSeparavel(40, 64, passo=2), _BlocoSeparavel(64, 96))
        self.d3 = _BlocoSeparavel(96 + 40, 48)
        self.d2 = _BlocoSeparavel(48 + 24, 32)
        self.d1 = _BlocoSeparavel(32 + 16, 24)
        self.saida = nn.Sequential(
            _ConvBnAtivacao(24, 16),
            nn.Conv2d(16, 1, kernel_size=1),
        )

    @staticmethod
    def _subir(entrada: torch.Tensor, referencia: torch.Tensor) -> torch.Tensor:
        return nn.functional.interpolate(
            entrada,
            size=referencia.shape[-2:],
            mode="bilinear",
            align_corners=False,
        )

    def forward(self, entrada: torch.Tensor) -> torch.Tensor:
        e1 = self.e1(entrada)
        e2 = self.e2(e1)
        e3 = self.e3(e2)
        e4 = self.e4(e3)
        d3 = self.d3(torch.cat((self._subir(e4, e3), e3), dim=1))
        d2 = self.d2(torch.cat((self._subir(d3, e2), e2), dim=1))
        d1 = self.d1(torch.cat((self._subir(d2, e1), e1), dim=1))
        return nn.functional.interpolate(
            self.saida(d1),
            size=entrada.shape[-2:],
            mode="bilinear",
            align_corners=False,
        )


def criar_modelo(arquitetura: str, *, pretreinado: bool = True) -> nn.Module:
    """Cria uma das arquiteturas candidatas sem selecao pelo conjunto de teste."""

    if arquitetura == "linhanet":
        return LinhaNet()
    if arquitetura == "lraspp_mobilenet_v3_large":
        return SegmentadorLRASPP(pretreinado=pretreinado)
    raise ErroTreinamentoSegmentacao(f"Arquitetura desconhecida: {arquitetura}")


class PerdaBceDice(nn.Module):
    """Combina segmentacao e presenca para suprimir falsos positivos grandes."""

    def __init__(
        self,
        peso_bce: float,
        peso_dice: float,
        peso_presenca: float = 0.0,
        peso_negativo_presenca: float = 1.0,
        fracao_topk_presenca: float = 0.01,
    ) -> None:
        super().__init__()
        self.peso_bce = peso_bce
        self.peso_dice = peso_dice
        self.peso_presenca = peso_presenca
        self.peso_negativo_presenca = peso_negativo_presenca
        self.fracao_topk_presenca = fracao_topk_presenca
        self.bce = nn.BCEWithLogitsLoss()

    def forward(self, logits: torch.Tensor, alvo: torch.Tensor) -> torch.Tensor:
        bce = self.bce(logits, alvo)
        probabilidade = torch.sigmoid(logits)
        dimensoes = (1, 2, 3)
        intersecao = torch.sum(probabilidade * alvo, dim=dimensoes)
        denominador = torch.sum(probabilidade + alvo, dim=dimensoes)
        dice = 1.0 - torch.mean((2.0 * intersecao + 1.0) / (denominador + 1.0))
        base = self.peso_bce * bce + self.peso_dice * dice
        if self.peso_presenca <= 0:
            return base
        achatado = logits.flatten(start_dim=1)
        quantidade_topk = max(1, round(achatado.shape[1] * self.fracao_topk_presenca))
        logit_presenca = torch.topk(achatado, quantidade_topk, dim=1).values.mean(dim=1)
        alvo_presenca = (torch.sum(alvo, dim=dimensoes) > 0).to(logits.dtype)
        pesos = torch.where(
            alvo_presenca > 0,
            torch.ones_like(alvo_presenca),
            torch.full_like(alvo_presenca, self.peso_negativo_presenca),
        )
        perda_presenca = nn.functional.binary_cross_entropy_with_logits(
            logit_presenca,
            alvo_presenca,
            weight=pesos,
        )
        return base + self.peso_presenca * perda_presenca


class AcumuladorMetricas:
    """Metricas pixel a pixel e falsos positivos em quadros negativos."""

    def __init__(self, limiar: float, area_minima_negativo: float = 0.0) -> None:
        self.limiar = limiar
        self.area_minima_negativo = area_minima_negativo
        self.tp = self.fp = self.fn = self.tn = 0
        self.negativos = self.negativos_falsos = 0
        self.negativos_falsos_significativos = 0
        self.pixels_previstos_negativos = 0
        self.pixels_totais_negativos = 0

    def adicionar(self, logits: torch.Tensor, alvo: torch.Tensor) -> None:
        previsto = torch.sigmoid(logits) >= self.limiar
        esperado = alvo >= 0.5
        self.tp += int(torch.count_nonzero(previsto & esperado))
        self.fp += int(torch.count_nonzero(previsto & ~esperado))
        self.fn += int(torch.count_nonzero(~previsto & esperado))
        self.tn += int(torch.count_nonzero(~previsto & ~esperado))
        por_amostra = torch.sum(esperado, dim=(1, 2, 3))
        falso_por_amostra = torch.sum(previsto, dim=(1, 2, 3))
        negativos = por_amostra == 0
        self.negativos += int(torch.count_nonzero(negativos))
        self.negativos_falsos += int(torch.count_nonzero(negativos & (falso_por_amostra > 0)))
        pixels_por_amostra = previsto[0].numel()
        limite_significativo = max(
            1,
            int(np.ceil(pixels_por_amostra * self.area_minima_negativo)),
        )
        self.negativos_falsos_significativos += int(
            torch.count_nonzero(negativos & (falso_por_amostra >= limite_significativo))
        )
        self.pixels_previstos_negativos += int(torch.sum(falso_por_amostra[negativos]))
        self.pixels_totais_negativos += int(torch.count_nonzero(negativos)) * pixels_por_amostra

    def calcular(self) -> dict[str, float]:
        suave = 1e-9
        return {
            "dice": (2 * self.tp) / (2 * self.tp + self.fp + self.fn + suave),
            "iou": self.tp / (self.tp + self.fp + self.fn + suave),
            "precisao": self.tp / (self.tp + self.fp + suave),
            "recall": self.tp / (self.tp + self.fn + suave),
            "taxa_falso_positivo_negativos": self.negativos_falsos / (self.negativos + suave),
            "taxa_falso_positivo_negativos_significativos": (
                self.negativos_falsos_significativos / (self.negativos + suave)
            ),
            "area_media_prevista_negativos": (
                self.pixels_previstos_negativos / (self.pixels_totais_negativos + suave)
            ),
        }


def _semear_trabalhador(_id_trabalhador: int) -> None:
    semente = torch.initial_seed() % 2**32
    np.random.seed(semente)
    random.seed(semente)


def criar_carregadores(
    raiz_dataset: Path,
    configuracao: ConfiguracaoTreinamento,
    dispositivo: torch.device,
) -> tuple[DataLoader, DataLoader]:
    """Cria DataLoaders reproduziveis com validacao nunca aumentada."""

    gerador = torch.Generator().manual_seed(configuracao.semente)
    argumentos = {
        "batch_size": configuracao.lote,
        "num_workers": configuracao.trabalhadores,
        "pin_memory": dispositivo.type == "cuda",
        "worker_init_fn": _semear_trabalhador,
        "generator": gerador,
        "persistent_workers": configuracao.trabalhadores > 0,
    }
    dataset_treino = DatasetSegmentacaoLinha(raiz_dataset, configuracao, "treino")
    amostrador = None
    if configuracao.peso_amostra_negativa > 1.0:
        pesos = [
            configuracao.peso_amostra_negativa if item["tipo_quadro"] == "sem_linha" else 1.0
            for item in dataset_treino.amostras
        ]
        amostrador = WeightedRandomSampler(
            pesos,
            num_samples=len(pesos),
            replacement=True,
            generator=torch.Generator().manual_seed(configuracao.semente + 1),
        )
    treino = DataLoader(
        dataset_treino,
        shuffle=amostrador is None,
        sampler=amostrador,
        drop_last=False,
        **argumentos,
    )
    validacao = DataLoader(
        DatasetSegmentacaoLinha(raiz_dataset, configuracao, "validacao"),
        shuffle=False,
        drop_last=False,
        **argumentos,
    )
    return treino, validacao


def _avaliar(
    modelo: nn.Module,
    carregador: DataLoader,
    perda_fn: nn.Module,
    dispositivo: torch.device,
    limiar: float,
    area_minima_negativo: float = 0.0,
) -> tuple[float, dict[str, float]]:
    modelo.eval()
    acumulador = AcumuladorMetricas(limiar, area_minima_negativo)
    perdas = []
    with torch.inference_mode():
        for imagens, mascaras in carregador:
            imagens = imagens.to(dispositivo, non_blocking=True)
            mascaras = mascaras.to(dispositivo, non_blocking=True)
            logits = modelo(imagens)
            perdas.append(float(perda_fn(logits, mascaras)))
            acumulador.adicionar(logits, mascaras)
    return float(np.mean(perdas)), acumulador.calcular()


def treinar(
    raiz_dataset: Path,
    saida: Path,
    configuracao: ConfiguracaoTreinamento,
    *,
    arquitetura: str = "linhanet",
    pretreinado: bool = True,
    checkpoint_inicial: Path | None = None,
) -> dict[str, object]:
    """Treina, interrompe por validacao e salva somente o melhor checkpoint."""

    if saida.exists():
        raise ErroTreinamentoSegmentacao(f"Saida de experimento ja existe: {saida}")
    saida.mkdir(parents=True)
    torch.manual_seed(configuracao.semente)
    np.random.seed(configuracao.semente)
    random.seed(configuracao.semente)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(configuracao.semente)
    dispositivo = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    modelo = criar_modelo(arquitetura, pretreinado=pretreinado).to(dispositivo)
    sha256_checkpoint_inicial = None
    if checkpoint_inicial is not None:
        checkpoint_inicial = checkpoint_inicial.resolve()
        pacote_inicial = torch.load(checkpoint_inicial, map_location="cpu", weights_only=True)
        if pacote_inicial.get("arquitetura") != arquitetura:
            raise ErroTreinamentoSegmentacao("Arquitetura do checkpoint inicial incompativel")
        modelo.load_state_dict(pacote_inicial["estado_modelo"])
        sha256_checkpoint_inicial = hashlib.sha256(checkpoint_inicial.read_bytes()).hexdigest()
    treino_loader, validacao_loader = criar_carregadores(
        raiz_dataset,
        configuracao,
        dispositivo,
    )
    perda_fn = PerdaBceDice(
        configuracao.peso_bce,
        configuracao.peso_dice,
        configuracao.peso_presenca,
        configuracao.peso_negativo_presenca,
        configuracao.fracao_topk_presenca,
    )
    otimizador = torch.optim.AdamW(
        modelo.parameters(),
        lr=configuracao.taxa_aprendizado,
        weight_decay=configuracao.decaimento_peso,
    )
    escalador = torch.amp.GradScaler("cuda", enabled=dispositivo.type == "cuda")
    melhor_dice = -1.0
    melhor_pontuacao = -float("inf")
    melhor_fpr_significativo = 1.0
    sem_melhora = 0
    historico = []
    inicio = perf_counter()

    for epoca in range(1, configuracao.epocas + 1):
        modelo.train()
        perdas_treino = []
        for imagens, mascaras in treino_loader:
            imagens = imagens.to(dispositivo, non_blocking=True)
            mascaras = mascaras.to(dispositivo, non_blocking=True)
            otimizador.zero_grad(set_to_none=True)
            with torch.autocast(
                device_type=dispositivo.type,
                dtype=torch.float16,
                enabled=dispositivo.type == "cuda",
            ):
                logits = modelo(imagens)
                perda = perda_fn(logits, mascaras)
            escalador.scale(perda).backward()
            escalador.unscale_(otimizador)
            torch.nn.utils.clip_grad_norm_(modelo.parameters(), max_norm=2.0)
            escalador.step(otimizador)
            escalador.update()
            perdas_treino.append(float(perda.detach()))

        perda_validacao, metricas = _avaliar(
            modelo,
            validacao_loader,
            perda_fn,
            dispositivo,
            configuracao.limiar,
            configuracao.area_minima_negativo,
        )
        pontuacao = (
            metricas["dice"]
            - configuracao.peso_fpr_selecao
            * metricas["taxa_falso_positivo_negativos_significativos"]
        )
        registro = {
            "epoca": epoca,
            "perda_treino": float(np.mean(perdas_treino)),
            "perda_validacao": perda_validacao,
            "pontuacao_selecao": pontuacao,
            **metricas,
        }
        historico.append(registro)
        print(json.dumps(registro, ensure_ascii=False), flush=True)
        if pontuacao > melhor_pontuacao:
            melhor_dice = metricas["dice"]
            melhor_pontuacao = pontuacao
            melhor_fpr_significativo = metricas["taxa_falso_positivo_negativos_significativos"]
            sem_melhora = 0
            torch.save(
                {
                    "arquitetura": arquitetura,
                    "estado_modelo": modelo.state_dict(),
                    "configuracao": asdict(configuracao),
                    "metricas_validacao": registro,
                },
                saida / "melhor.pt",
            )
        else:
            sem_melhora += 1
            if sem_melhora >= configuracao.paciencia:
                break

    manifesto: dict[str, object] = {
        "versao_manifesto": 1,
        "arquitetura": arquitetura,
        "dispositivo_treino": str(dispositivo),
        "torch": torch.__version__,
        "configuracao": asdict(configuracao),
        "melhor_dice_validacao": melhor_dice,
        "melhor_pontuacao_selecao": melhor_pontuacao,
        "fpr_significativo_checkpoint": melhor_fpr_significativo,
        "sha256_checkpoint_inicial": sha256_checkpoint_inicial,
        "epocas_executadas": len(historico),
        "duracao_s": round(perf_counter() - inicio, 3),
        "teste_aberto": False,
    }
    (saida / "historico.jsonl").write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in historico),
        encoding="utf-8",
    )
    (saida / "manifesto.json").write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifesto
