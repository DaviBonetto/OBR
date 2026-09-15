const $ = (seletor) => document.querySelector(seletor);
const percentual = (valor) => `${(100 * (valor ?? 0)).toFixed(1)}%`;
const numero = (valor, casas = 1, sufixo = "") => valor == null ? "—" : `${valor.toFixed(casas)}${sufixo}`;
const rotulo = (valor) => (valor ?? "—").replaceAll("_", " ").toUpperCase();

function atualizarEstado(dados) {
  const processador = dados.processador;
  $("#fps-percepcao").textContent = numero(processador.quadros_por_segundo, 1, " FPS");
  $("#fps-camera").textContent = numero(dados.camera.quadros_por_segundo_medido, 1, " FPS");
  if (!dados.percepcao) return;

  const estimativa = dados.percepcao.estimativa;
  const diagnostico = dados.percepcao.diagnostico;
  $("#estado").textContent = rotulo(estimativa.estado);
  $("#indicador").className = `indicador ${estimativa.estado}`;
  $("#confianca").textContent = percentual(estimativa.confianca);
  $("#barra-confianca").style.width = percentual(estimativa.confianca);
  $("#motivo").textContent = estimativa.motivo.replaceAll("_", " ");
  $("#curva").textContent = rotulo(estimativa.tipo_curva);
  $("#fonte").textContent = rotulo(estimativa.fonte);
  $("#erro-lateral").textContent = numero(estimativa.erro_lateral_normalizado, 3);
  $("#erro-angular").textContent = numero(estimativa.erro_angular_graus, 1, "°");
  $("#inferencia").textContent = numero(estimativa.tempos.inferencia_ms, 2, " ms");
  $("#geometria").textContent = numero(estimativa.tempos.geometria_ms, 2, " ms");
  $("#tempo-total").textContent = numero(estimativa.tempos.total_ms, 2, " ms");
  $("#intersecao").textContent = diagnostico.intersecao_detectada
    ? "SIM · LINHA RETA"
    : "NÃO";
  $("#cobertura").textContent = percentual(diagnostico.cobertura_faixas);
  $("#area").textContent = percentual(diagnostico.area_mascara);
  $("#idade").textContent = numero(estimativa.idade_observacao_ms, 0, " ms");
  const verde = dados.percepcao.verde;
  const evidenciaPrevia = verde?.motivo?.startsWith("evidencia_verde_antes_do_t_");
  const decisaoPrevia = evidenciaPrevia
    ? verde.motivo.replace("evidencia_verde_antes_do_t_", "")
    : null;
  $("#verde-estado").textContent = evidenciaPrevia
    ? "PRÉ-T DETECTADO"
    : verde
      ? rotulo(verde.estado)
      : "INDISPONÍVEL";
  $("#verde-decisao").textContent = decisaoPrevia
    ? `AGUARDANDO T · ${rotulo(decisaoPrevia)}`
    : verde
      ? rotulo(verde.decisao)
      : "—";
  $("#verde-marcadores").textContent = verde ? String(verde.marcadores.length) : "—";
  $("#verde-confianca").textContent = verde ? percentual(verde.confianca) : "—";
  $("#verde-inferencia").textContent = verde
    ? numero(verde.tempos.inferencia_ms, 2, " ms")
    : "—";
  $("#verde-motivo").textContent = verde
    ? verde.motivo.replaceAll("_", " ")
    : "Detector verde não iniciado";
}

async function consultar() {
  try {
    const resposta = await fetch("/api/estado", { cache: "no-store" });
    if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
    atualizarEstado(await resposta.json());
  } catch (_) {
    $("#estado").textContent = "DESCONECTADO";
    $("#indicador").className = "indicador perdida";
  }
}

consultar();
setInterval(consultar, 150);
