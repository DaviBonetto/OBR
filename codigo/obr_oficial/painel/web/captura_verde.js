const CATEGORIAS = [
  "antes_esquerda",
  "antes_direita",
  "dois_antes_180",
  "depois_ignorar",
  "sem_verde_negativo",
];

const DECISOES = {
  antes_esquerda: "VIRAR À ESQUERDA",
  antes_direita: "VIRAR À DIREITA",
  dois_antes_180: "RETORNAR 180°",
  depois_ignorar: "IGNORAR · LINHA NORMAL",
  sem_verde_negativo: "SEM COMANDO · LINHA NORMAL",
};

const elementos = {
  indicadorCamera: document.querySelector("#indicador-camera"),
  textoCamera: document.querySelector("#texto-camera"),
  perfilCamera: document.querySelector("#perfil-camera"),
  nomeDispositivo: document.querySelector("#nome-dispositivo"),
  resolucao: document.querySelector("#resolucao"),
  estadoSessao: document.querySelector("#estado-sessao"),
  contadorFotos: document.querySelector("#contador-fotos"),
  fps: document.querySelector("#fps"),
  brilho: document.querySelector("#brilho"),
  claro: document.querySelector("#claro"),
  escuro: document.querySelector("#escuro"),
  nitidez: document.querySelector("#nitidez"),
  armazenamento: document.querySelector("#armazenamento"),
  alertasImagem: document.querySelector("#alertas-imagem"),
  idadeQuadro: document.querySelector("#idade-quadro"),
  nome: document.querySelector("#nome"),
  local: document.querySelector("#local"),
  iluminacao: document.querySelector("#iluminacao"),
  piso: document.querySelector("#piso"),
  leds: document.querySelector("#leds"),
  observacoes: document.querySelector("#observacoes"),
  cruzMista: document.querySelector("#cruz-mista"),
  campoCruzMista: document.querySelector("#campo-cruz-mista"),
  decisaoEsperada: document.querySelector("#decisao-esperada"),
  notaQuadro: document.querySelector("#nota-quadro"),
  intervalo: document.querySelector("#intervalo"),
  iniciar: document.querySelector("#iniciar"),
  capturar: document.querySelector("#capturar"),
  sequencia: document.querySelector("#sequencia"),
  finalizar: document.querySelector("#finalizar"),
  mensagem: document.querySelector("#mensagem"),
};

let sessaoAtiva = false;
let capturaEmAndamento = false;
let temporizadorSequencia = null;

async function requisitar(caminho, opcoes = {}) {
  const resposta = await fetch(caminho, {
    headers: { "Content-Type": "application/json" },
    ...opcoes,
  });
  const dados = await resposta.json();
  if (!resposta.ok || dados.ok === false) {
    throw new Error(dados.erro || `Falha HTTP ${resposta.status}`);
  }
  return dados;
}

function categoriaSelecionada() {
  return document.querySelector('input[name="categoria-verde"]:checked')?.value;
}

function contextoSessao() {
  return {
    nome: elementos.nome.value.trim(),
    local: elementos.local.value.trim(),
    iluminacao: elementos.iluminacao.value,
    piso: elementos.piso.value,
    leds: elementos.leds.checked,
    observacoes: elementos.observacoes.value.trim(),
  };
}

function contextoQuadro() {
  return {
    categoria_verde: categoriaSelecionada(),
    cruz_mista: elementos.cruzMista.checked,
    nota: elementos.notaQuadro.value.trim(),
  };
}

function informar(texto, tipo = "") {
  elementos.mensagem.textContent = texto;
  elementos.mensagem.className = `mensagem ${tipo}`.trim();
}

function atualizarBotoes() {
  elementos.iniciar.disabled = sessaoAtiva;
  elementos.capturar.disabled = !sessaoAtiva;
  elementos.sequencia.disabled = !sessaoAtiva;
  elementos.finalizar.disabled = !sessaoAtiva;
  elementos.estadoSessao.textContent = sessaoAtiva ? "SESSÃO VERDE ATIVA" : "SEM SESSÃO";
  elementos.estadoSessao.classList.toggle("ativo", sessaoAtiva);
}

function atualizarCategoria() {
  const categoria = categoriaSelecionada();
  const aceitaCruzMista = ["antes_esquerda", "antes_direita", "dois_antes_180"].includes(
    categoria,
  );
  elementos.cruzMista.disabled = !aceitaCruzMista;
  if (!aceitaCruzMista) elementos.cruzMista.checked = false;
  elementos.campoCruzMista.classList.toggle("desabilitado", !aceitaCruzMista);
  elementos.decisaoEsperada.textContent = `DECISÃO · ${DECISOES[categoria]}`;
}

function atualizarContagens(contagens = {}) {
  for (const categoria of CATEGORIAS) {
    const destino = document.querySelector(`#contagem-${categoria}`);
    destino.textContent = Number(contagens[categoria] || 0).toLocaleString("pt-BR");
  }
}

function atualizarAlertasImagem(metricas) {
  const alertas = [];
  const brilho = Number(metricas.brilho_medio);
  const escuro = Number(metricas.percentual_escuro);
  const claro = Number(metricas.percentual_claro);
  const nitidez = Number(metricas.nitidez_laplaciano);

  if (brilho < 35 || escuro > 55) {
    alertas.push("Condição muito escura. Capture se ela for intencional e registre a iluminação.");
  }
  if (brilho > 225 || claro > 35) {
    alertas.push("Condição muito clara. Capture se ela for intencional e evite perda total do marcador.");
  }
  if (nitidez < 25) {
    alertas.push("Nitidez muito baixa. Movimento real é útil; lente suja ou foco incorreto não é.");
  }

  elementos.alertasImagem.replaceChildren();
  elementos.alertasImagem.classList.toggle("oculto", alertas.length === 0);
  for (const alerta of alertas) {
    const item = document.createElement("p");
    item.textContent = alerta;
    elementos.alertasImagem.append(item);
  }
}

async function iniciarSessao() {
  const contexto = contextoSessao();
  if (!contexto.nome || !contexto.local) {
    informar("Preencha o nome da sessão e o local antes de iniciar.", "erro");
    return;
  }
  try {
    await requisitar("/api/sessoes", {
      method: "POST",
      body: JSON.stringify({ contexto }),
    });
    sessaoAtiva = true;
    atualizarBotoes();
    informar("Sessão verde iniciada. Escolha a categoria e capture.", "sucesso");
    await atualizarEstado();
  } catch (erro) {
    informar(erro.message, "erro");
  }
}

async function capturarFoto({ silenciosa = false } = {}) {
  if (!sessaoAtiva || capturaEmAndamento) return;
  capturaEmAndamento = true;
  try {
    const dados = await requisitar("/api/capturas", {
      method: "POST",
      body: JSON.stringify({ contexto: contextoQuadro() }),
    });
    const numero = dados.registro.numero;
    elementos.contadorFotos.textContent = `${numero} ${numero === 1 ? "foto" : "fotos"}`;
    if (!silenciosa) informar(`Foto ${numero} salva com rótulo verde.`, "sucesso");
    await atualizarEstado();
  } catch (erro) {
    informar(erro.message, "erro");
    pararSequencia();
  } finally {
    capturaEmAndamento = false;
  }
}

function alternarSequencia() {
  if (temporizadorSequencia !== null) {
    pararSequencia();
    informar("Sequência automática interrompida.");
    return;
  }
  const intervalo = Number(elementos.intervalo.value);
  temporizadorSequencia = window.setInterval(
    () => capturarFoto({ silenciosa: true }),
    intervalo,
  );
  elementos.sequencia.textContent = "Parar sequência";
  informar(`Sequência ativa: ${DECISOES[categoriaSelecionada()]}.`, "sucesso");
  capturarFoto({ silenciosa: true });
}

function pararSequencia() {
  if (temporizadorSequencia !== null) {
    window.clearInterval(temporizadorSequencia);
    temporizadorSequencia = null;
  }
  elementos.sequencia.textContent = "Iniciar sequência";
}

async function finalizarSessao() {
  pararSequencia();
  try {
    await requisitar("/api/sessoes/atual/finalizar", { method: "POST", body: "{}" });
    sessaoAtiva = false;
    atualizarBotoes();
    informar("Sessão finalizada e manifesto verde salvo.", "sucesso");
    await atualizarEstado();
  } catch (erro) {
    informar(erro.message, "erro");
  }
}

async function atualizarEstado() {
  try {
    const dados = await requisitar("/api/estado");
    if (dados.modo_captura !== "verde") throw new Error("servidor não está no modo verde");
    const camera = dados.camera;
    const quadro = dados.quadro;
    const captura = dados.captura;
    sessaoAtiva = Boolean(captura.ativa);
    atualizarBotoes();

    elementos.indicadorCamera.className = `indicador ${camera.saudavel ? "ativo" : "erro"}`;
    elementos.textoCamera.textContent = camera.saudavel ? "Câmera saudável" : "Câmera sem quadro recente";
    elementos.perfilCamera.textContent = camera.nome_perfil;
    elementos.nomeDispositivo.textContent = camera.nome_dispositivo;
    elementos.resolucao.textContent = `${camera.largura} × ${camera.altura}`;
    elementos.fps.textContent = Number(camera.quadros_por_segundo_medido).toFixed(1);
    elementos.idadeQuadro.textContent = `Idade do quadro: ${formatarMs(camera.idade_ultimo_quadro_ms)}`;
    elementos.armazenamento.textContent = formatarBytes(dados.armazenamento.livre_bytes);

    if (quadro) {
      elementos.brilho.textContent = Number(quadro.metricas.brilho_medio).toFixed(0);
      elementos.claro.textContent = `${Number(quadro.metricas.percentual_claro).toFixed(1)}%`;
      elementos.escuro.textContent = `${Number(quadro.metricas.percentual_escuro).toFixed(1)}%`;
      elementos.nitidez.textContent = Number(quadro.metricas.nitidez_laplaciano).toFixed(0);
      atualizarAlertasImagem(quadro.metricas);
    } else {
      elementos.alertasImagem.classList.add("oculto");
    }
    const quantidade = captura.sessao?.capturas || 0;
    elementos.contadorFotos.textContent = `${quantidade} ${quantidade === 1 ? "foto" : "fotos"}`;
    atualizarContagens(captura.sessao?.contagens_por_categoria);
  } catch (erro) {
    elementos.indicadorCamera.className = "indicador erro";
    elementos.textoCamera.textContent = "Painel desconectado";
    informar(`Sem comunicação: ${erro.message}`, "erro");
  }
}

function formatarMs(valor) {
  if (valor === null || valor === undefined) return "—";
  return `${Number(valor).toFixed(0)} ms`;
}

function formatarBytes(valor) {
  const unidades = ["B", "KB", "MB", "GB", "TB"];
  let numero = Number(valor);
  let indice = 0;
  while (numero >= 1024 && indice < unidades.length - 1) {
    numero /= 1024;
    indice += 1;
  }
  return `${numero.toFixed(indice < 2 ? 0 : 1)} ${unidades[indice]}`;
}

elementos.iniciar.addEventListener("click", iniciarSessao);
elementos.capturar.addEventListener("click", () => capturarFoto());
elementos.sequencia.addEventListener("click", alternarSequencia);
elementos.finalizar.addEventListener("click", finalizarSessao);
document.querySelectorAll('input[name="categoria-verde"]').forEach((entrada) => {
  entrada.addEventListener("change", atualizarCategoria);
});

window.addEventListener("keydown", (evento) => {
  const tag = document.activeElement?.tagName;
  if (["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(tag)) return;
  if (evento.code === "Space") {
    evento.preventDefault();
    capturarFoto();
    return;
  }
  const indice = Number(evento.key) - 1;
  if (indice >= 0 && indice < CATEGORIAS.length) {
    const entrada = document.querySelector(`input[value="${CATEGORIAS[indice]}"]`);
    entrada.checked = true;
    atualizarCategoria();
  }
});

window.addEventListener("beforeunload", pararSequencia);
atualizarCategoria();
atualizarBotoes();
atualizarEstado();
window.setInterval(atualizarEstado, 750);
