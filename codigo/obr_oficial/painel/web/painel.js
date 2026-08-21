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
  tipoQuadro: document.querySelector("#tipo-quadro"),
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
    tipo_quadro: elementos.tipoQuadro.value,
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
  elementos.estadoSessao.textContent = sessaoAtiva ? "SESSÃO ATIVA" : "SEM SESSÃO";
  elementos.estadoSessao.classList.toggle("ativo", sessaoAtiva);
}

function atualizarAlertasImagem(metricas) {
  const alertas = [];
  const brilho = Number(metricas.brilho_medio);
  const escuro = Number(metricas.percentual_escuro);
  const claro = Number(metricas.percentual_claro);
  const nitidez = Number(metricas.nitidez_laplaciano);

  if (brilho < 35 || escuro > 55) {
    alertas.push("Imagem muito escura: descubra a lente, afaste-a do piso ou melhore a iluminação.");
  }
  if (brilho > 225 || claro > 35) {
    alertas.push("Imagem muito clara: evite reflexo direto e reduza a iluminação sobre o piso.");
  }
  if (nitidez < 25) {
    alertas.push("Nitidez baixa: limpe a lente, ajuste o foco e mantenha o robô imóvel.");
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
    informar("Sessão iniciada. Posicione o robô e capture os quadros.", "sucesso");
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
    if (!silenciosa) informar(`Foto ${numero} salva em PNG.`, "sucesso");
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
  informar(`Sequência automática ativa a cada ${intervalo} ms.`, "sucesso");
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
    await requisitar("/api/sessoes/atual/finalizar", {
      method: "POST",
      body: "{}",
    });
    sessaoAtiva = false;
    atualizarBotoes();
    informar("Sessão finalizada e manifesto salvo.", "sucesso");
    await atualizarEstado();
  } catch (erro) {
    informar(erro.message, "erro");
  }
}

async function atualizarEstado() {
  try {
    const dados = await requisitar("/api/estado");
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

window.addEventListener("keydown", (evento) => {
  const tag = document.activeElement?.tagName;
  if (evento.code === "Space" && !["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(tag)) {
    evento.preventDefault();
    capturarFoto();
  }
});

window.addEventListener("beforeunload", pararSequencia);
atualizarBotoes();
atualizarEstado();
window.setInterval(atualizarEstado, 750);
