const estado = {
  indice: 0,
  total: 0,
  amostra: null,
  pontos: [],
  previsao: null,
  imagem: null,
};
const $ = (seletor) => document.querySelector(seletor);
const canvas = $("#canvas");
const contexto = canvas.getContext("2d");

function parametros() {
  return new URLSearchParams({
    indice: estado.indice,
    tipo: $("#tipo").value,
    estado: $("#estado-filtro").value,
  });
}

function nomeTipo(tipo) {
  return ({
    reta: "Linha reta",
    curva_aberta: "Curva aberta",
    curva_fechada: "Curva fechada / 90°",
    intersecao: "Interseção T · seguir reto",
  })[tipo] || tipo;
}

function atualizarResumo(resumo) {
  $("#progresso").textContent = `${resumo.anotadas} / ${resumo.total} anotadas · ${resumo.pendentes} pendentes`;
}

function desenharLinha(pontos, cor, largura, bolinhas = false) {
  if (!pontos || !pontos.length) return;
  contexto.save();
  contexto.strokeStyle = cor;
  contexto.lineWidth = largura;
  contexto.lineJoin = "round";
  contexto.lineCap = "round";
  contexto.beginPath();
  pontos.forEach((ponto, indice) => {
    const x = ponto.x * canvas.width;
    const y = ponto.y * canvas.height;
    if (indice === 0) contexto.moveTo(x, y); else contexto.lineTo(x, y);
  });
  contexto.stroke();
  if (bolinhas) {
    pontos.forEach((ponto, indice) => {
      const x = ponto.x * canvas.width;
      const y = ponto.y * canvas.height;
      contexto.beginPath();
      contexto.fillStyle = indice === 0 ? "#ffffff" : cor;
      contexto.arc(x, y, indice === 0 ? 5 : 3.2, 0, Math.PI * 2);
      contexto.fill();
      contexto.lineWidth = 1.5;
      contexto.strokeStyle = "#061012";
      contexto.stroke();
    });
  }
  contexto.restore();
}

function redesenhar() {
  contexto.clearRect(0, 0, canvas.width, canvas.height);
  if (!estado.imagem) return;
  contexto.drawImage(estado.imagem, 0, 0, canvas.width, canvas.height);
  if ($("#mostrar-ia").checked && estado.previsao) {
    desenharLinha(estado.previsao.centro_linha, "#ff6548", 2.5);
  }
  desenharLinha(estado.pontos, "#33e4ef", 3.2, true);
}

async function carregarImagem(indiceOriginal) {
  const imagem = new Image();
  imagem.src = `/api/imagem/${indiceOriginal}?v=${Date.now()}`;
  await imagem.decode();
  estado.imagem = imagem;
  canvas.width = imagem.naturalWidth;
  canvas.height = imagem.naturalHeight;
  redesenhar();
}

async function carregarPrevisao() {
  if (!estado.amostra || estado.previsao) return;
  const resposta = await fetch(`/api/previsao/${estado.amostra.indice_original}`);
  const dados = await resposta.json();
  if (!dados.ok) throw new Error(dados.erro);
  estado.previsao = dados.estimativa;
  redesenhar();
}

function renderizar(dados) {
  estado.total = dados.total;
  estado.indice = dados.indice;
  estado.amostra = dados.amostra;
  estado.previsao = null;
  estado.imagem = null;
  atualizarResumo(dados.resumo);
  $("#posicao").textContent = dados.total ? `${dados.indice + 1} / ${dados.total}` : "0 / 0";
  $("#anterior").disabled = !dados.total || dados.indice === 0;
  $("#proxima").disabled = !dados.total || dados.indice >= dados.total - 1;
  canvas.style.display = dados.amostra ? "block" : "none";
  $("#vazio").style.display = dados.amostra ? "none" : "block";
  if (!dados.amostra) {
    estado.pontos = [];
    redesenhar();
    return;
  }

  const amostra = dados.amostra;
  estado.pontos = (amostra.anotacao_atual?.pontos || []).map((ponto) => ({ ...ponto }));
  $("#nome-tipo").textContent = nomeTipo(amostra.tipo_quadro);
  $("#metadados").textContent = `validação · ${amostra.id_amostra}`;
  $("#observacao").value = amostra.anotacao_atual?.observacao || "";
  $("#mostrar-ia").checked = false;
  $("#instrucao").textContent = amostra.tipo_quadro === "intersecao"
    ? "Interseção T: marque do robô para a continuação reta, sem entrar nos braços laterais."
    : "Clique no centro da linha, começando perto do robô e seguindo até o destino.";
  carregarImagem(amostra.indice_original).catch(mostrarErro);
}

async function carregar() {
  $("#mensagem").textContent = "";
  const resposta = await fetch(`/api/amostra?${parametros()}`);
  const dados = await resposta.json();
  if (!dados.ok) throw new Error(dados.erro);
  renderizar(dados);
}

canvas.addEventListener("pointerdown", (evento) => {
  if (!estado.amostra) return;
  const retangulo = canvas.getBoundingClientRect();
  estado.pontos.push({
    x: Math.max(0, Math.min(1, (evento.clientX - retangulo.left) / retangulo.width)),
    y: Math.max(0, Math.min(1, (evento.clientY - retangulo.top) / retangulo.height)),
  });
  redesenhar();
});

$("#desfazer").addEventListener("click", () => { estado.pontos.pop(); redesenhar(); });
$("#limpar").addEventListener("click", () => { estado.pontos = []; redesenhar(); });
$("#mostrar-ia").addEventListener("change", () => {
  if ($("#mostrar-ia").checked) carregarPrevisao().catch(mostrarErro); else redesenhar();
});

async function salvar() {
  if (!estado.amostra) return;
  const resposta = await fetch("/api/anotacoes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      id_amostra: estado.amostra.id_amostra,
      pontos: estado.pontos,
      observacao: $("#observacao").value,
    }),
  });
  const dados = await resposta.json();
  if (!dados.ok) throw new Error(dados.erro);
  $("#mensagem").textContent = "Referência salva.";
  if ($("#estado-filtro").value === "pendentes") estado.indice = 0;
  else if (estado.indice < estado.total - 1) estado.indice += 1;
  await carregar();
}

$("#salvar").addEventListener("click", () => salvar().catch(mostrarErro));

[$("#tipo"), $("#estado-filtro")].forEach((campo) => {
  campo.addEventListener("change", () => { estado.indice = 0; carregar().catch(mostrarErro); });
});
$("#anterior").addEventListener("click", () => { estado.indice -= 1; carregar().catch(mostrarErro); });
$("#proxima").addEventListener("click", () => { estado.indice += 1; carregar().catch(mostrarErro); });
document.addEventListener("keydown", (evento) => {
  if ((evento.ctrlKey || evento.metaKey) && evento.key.toLowerCase() === "z") {
    evento.preventDefault();
    estado.pontos.pop();
    redesenhar();
  }
});

function mostrarErro(erro) { $("#mensagem").textContent = erro.message; }
carregar().catch(mostrarErro);
