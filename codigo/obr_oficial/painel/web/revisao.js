const estado = { indice: 0, total: 0, amostra: null, modo: "sobreposicao" };
const $ = (seletor) => document.querySelector(seletor);

function filtros() {
  return new URLSearchParams({
    indice: estado.indice,
    divisao: $("#divisao").value,
    tipo: $("#tipo").value,
    revisao: $("#revisao").value,
  });
}

function nomeTipo(tipo) {
  return ({
    reta: "Linha reta",
    curva_aberta: "Curva aberta",
    curva_fechada: "Curva fechada",
    intersecao: "Interseção T · seguir reto",
    sem_linha: "Sem linha / negativo",
  })[tipo] || tipo;
}

function nomeDecisao(decisao) {
  return ({
    aprovada: "Linha presente · máscara correta",
    mascara_vazia: "Sem linha · manter vazia",
    reprocessar: "Linha presente · corrigir máscara",
  })[decisao] || decisao || "Pendente";
}

function nomeMotivo(motivo) {
  return ({
    rotulo_vazio_manual: "Máscara vazia marcada manualmente",
    rotulo_vazio_manual_e_desacordo_modelo: "Máscara vazia manual contestada pela IA",
    desacordo_modelo_com_negativo: "Negativo contestado pela IA",
  })[motivo] || motivo;
}

function atualizarResumo(resumo) {
  const revisadas = resumo.total - resumo.pendente;
  $("#progresso").textContent = `${revisadas} revisadas · ${resumo.pendente} pendentes`;
}

function renderizar(dados) {
  estado.total = dados.total;
  estado.indice = dados.indice;
  estado.amostra = dados.amostra;
  atualizarResumo(dados.resumo);
  $("#posicao").textContent = dados.total ? `${dados.indice + 1} / ${dados.total}` : "0 / 0";
  $("#anterior").disabled = !dados.total || dados.indice === 0;
  $("#proxima").disabled = !dados.total || dados.indice >= dados.total - 1;
  $("#imagem").style.display = dados.amostra ? "block" : "none";
  $("#vazio").style.display = dados.amostra ? "none" : "block";
  if (!dados.amostra) return;

  const a = dados.amostra;
  $("#nome-tipo").textContent = nomeTipo(a.tipo_quadro);
  const motivo = a.motivo_auditoria ? ` · ${nomeMotivo(a.motivo_auditoria)}` : "";
  $("#metadados").textContent = `${a.divisao} · ${a.origem}${motivo}`;
  $("#confianca").textContent = `${(a.confianca * 100).toFixed(1)}%`;
  $("#latencia").textContent = `${a.latencia_ms.toFixed(2)} ms`;
  $("#estado").textContent = a.estado;
  $("#decisao-atual").textContent = nomeDecisao(a.revisao_atual?.decisao);
  $("#observacao").value = a.revisao_atual?.observacao || "";
  atualizarImagem();
}

function atualizarImagem() {
  if (!estado.amostra) return;
  const versao = Date.now();
  $("#imagem").src = `/api/imagem/${estado.amostra.indice_original}/${estado.modo}?v=${versao}`;
}

async function carregar() {
  $("#mensagem").textContent = "";
  const resposta = await fetch(`/api/amostra?${filtros()}`);
  const dados = await resposta.json();
  if (!dados.ok) throw new Error(dados.erro);
  renderizar(dados);
}

async function revisar(decisao) {
  if (!estado.amostra) return;
  const resposta = await fetch("/api/revisoes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      id_amostra: estado.amostra.id_amostra,
      decisao,
      observacao: $("#observacao").value,
    }),
  });
  const dados = await resposta.json();
  if (!dados.ok) throw new Error(dados.erro);
  $("#mensagem").textContent = "Revisão salva.";
  if (estado.indice < estado.total - 1) estado.indice += 1;
  await carregar();
}

document.querySelectorAll(".modos button").forEach((botao) => {
  botao.addEventListener("click", () => {
    estado.modo = botao.dataset.modo;
    document.querySelectorAll(".modos button").forEach((item) => item.classList.remove("ativo"));
    botao.classList.add("ativo");
    atualizarImagem();
  });
});

document.querySelectorAll("[data-decisao]").forEach((botao) => {
  botao.addEventListener("click", () => revisar(botao.dataset.decisao).catch(mostrarErro));
});

[$("#divisao"), $("#tipo"), $("#revisao")].forEach((campo) => {
  campo.addEventListener("change", () => { estado.indice = 0; carregar().catch(mostrarErro); });
});

$("#anterior").addEventListener("click", () => { estado.indice -= 1; carregar().catch(mostrarErro); });
$("#proxima").addEventListener("click", () => { estado.indice += 1; carregar().catch(mostrarErro); });

function mostrarErro(erro) { $("#mensagem").textContent = erro.message; }
carregar().catch(mostrarErro);
