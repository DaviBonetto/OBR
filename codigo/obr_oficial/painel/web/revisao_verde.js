const estado = { indice: 0, total: 0, amostra: null, modo: "sobreposicao", salvando: false };
const $ = (seletor) => document.querySelector(seletor);

function parametros() {
  return new URLSearchParams({
    indice: estado.indice,
    divisao: $("#divisao").value,
    categoria: $("#categoria").value,
    prioridade: $("#prioridade").value,
    revisao: $("#revisao").value,
  });
}

function nomeCategoria(categoria, mista) {
  const nome = ({
    antes_esquerda: "Antes · esquerda",
    antes_direita: "Antes · direita",
    dois_antes_180: "Dois antes · retorno 180°",
    depois_ignorar: "Depois · detectar e ignorar",
    sem_verde_negativo: "Sem verde · máscara vazia",
  })[categoria] || categoria;
  return mista ? `${nome} · cruz mista` : nome;
}

function nomeDecisao(decisao) {
  return ({
    pendente: "Pendente",
    aprovada: "Máscara correta",
    mascara_vazia: "Máscara vazia",
    reprocessar: "Precisa corrigir",
    aprovada_vazia_por_contrato: "Vazia por contrato",
  })[decisao] || decisao;
}

function nomeMotivo(motivo) {
  return ({
    area_fora_da_faixa: "área fora da faixa",
    componente_extra_ambiguo: "região extra parecida com verde",
    componentes_insuficientes: "faltam componentes",
    confianca_baixa: "confiança baixa",
    forma_irregular: "forma irregular",
    marcador_parcial_na_borda: "marcador parcial na borda",
    mascara_vazia_por_contrato: "vazia por contrato humano",
  })[motivo] || motivo;
}

function atualizarResumo(resumo) {
  const revisadas = resumo.aprovada || 0;
  const corrigir = resumo.reprocessar || 0;
  $("#progresso").textContent = `${resumo.fila_revisao_essencial || 0} representantes · ${revisadas} aprovadas · ${corrigir} para corrigir`;
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
  $("#nome-categoria").textContent = nomeCategoria(a.categoria_verde, a.cruz_mista);
  $("#metadados").textContent = `${a.divisao} · ${a.origem}`;
  $("#confianca").textContent = `${(a.confianca_bootstrap * 100).toFixed(1)}%`;
  $("#area").textContent = `${(a.area_mascara_normalizada * 100).toFixed(2)}%`;
  $("#esperados").textContent = a.quantidade_marcadores_esperada;
  $("#selecionados").textContent = a.quantidade_componentes_selecionada;
  $("#prioridade-atual").textContent = a.prioridade;
  $("#motivos").textContent = a.motivos_prioridade.length
    ? a.motivos_prioridade.map(nomeMotivo).join(" · ")
    : "sem alerta automático";
  $("#decisao-atual").textContent = nomeDecisao(a.estado_revisao);
  $("#grupo-revisao").textContent = a.grupo_revisao
    ? `${a.grupo_revisao}${a.fila_revisao_essencial ? " · representante" : ""}`
    : "fora da fila essencial";
  $("#observacao").value = a.revisao_atual?.observacao || "";
  atualizarImagem();
}

function atualizarImagem() {
  if (!estado.amostra) return;
  $("#imagem").src = `/api/imagem/${estado.amostra.indice_original}/${estado.modo}?v=${Date.now()}`;
}

async function carregar() {
  $("#mensagem").textContent = "";
  const resposta = await fetch(`/api/amostra?${parametros()}`);
  const dados = await resposta.json();
  if (!dados.ok) throw new Error(dados.erro);
  renderizar(dados);
}

async function revisar(decisao) {
  if (!estado.amostra || estado.salvando) return;
  estado.salvando = true;
  try {
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
    await carregar();
  } finally {
    estado.salvando = false;
  }
}

function navegar(delta) {
  estado.indice = Math.max(0, Math.min(estado.total - 1, estado.indice + delta));
  carregar().catch(mostrarErro);
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

[$("#divisao"), $("#categoria"), $("#prioridade"), $("#revisao")].forEach((campo) => {
  campo.addEventListener("change", () => {
    estado.indice = 0;
    carregar().catch(mostrarErro);
  });
});

$("#anterior").addEventListener("click", () => navegar(-1));
$("#proxima").addEventListener("click", () => navegar(1));
document.addEventListener("keydown", (evento) => {
  if (evento.target.matches("textarea, select, input")) return;
  if (evento.key === "ArrowLeft") navegar(-1);
  if (evento.key === "ArrowRight") navegar(1);
  if (evento.key.toLowerCase() === "a") revisar("aprovada").catch(mostrarErro);
  if (evento.key.toLowerCase() === "v") revisar("mascara_vazia").catch(mostrarErro);
  if (evento.key.toLowerCase() === "r") revisar("reprocessar").catch(mostrarErro);
});

function mostrarErro(erro) { $("#mensagem").textContent = erro.message; }
carregar().catch(mostrarErro);
