/* OBR · Painel de operacao — v5 (desenho do dono).
   Topo com cronometro e recolher laterais; estado hero central;
   viradas renderizadas por cartao via data-grupo-viradas. */
"use strict";

(() => {
  const $ = (id) => document.getElementById(id);

  const elementos = {
    conexao: null, /* pill removida; o pulso no topo mostra a conexao */
    pulso: $("pulso-conexao"),
    alternarLaterais: $("alternar-laterais"),
    cronometro: $("cronometro"),
    video: $("video"),
    videoCru: $("video-cru"),
    avisoVideo: $("aviso-video"),
    placeholderPercepcao: $("placeholder-percepcao"),
    fps: $("m-fps"),
    quadro: $("m-quadro"),
    latencia: $("m-latencia"),
    estadoDot: $("estado-dot"),
    estadoTexto: $("estado-texto"),
    estadoConfianca: $("estado-confianca"),
    bLinha: $("b-linha"),
    bEsquerda: $("b-esquerda"),
    bDireita: $("b-direita"),
    sPercepcao: $("s-percepcao"),
    sProcessados: $("s-processados"),
    sCamera: $("s-camera"),
    sPerfil: $("s-perfil"),
    sResolucao: $("s-resolucao"),
    sAtivo: $("s-ativo"),
    sDisco: $("s-disco"),
    sCam0Estado: $("s-cam0-estado"),
    sCam0Fonte: $("s-cam0-fonte"),
    sCam0Video: $("s-cam0-video"),
    sRaspSubtensao: $("s-rasp-subtensao"),
    sRaspNucleo: $("s-rasp-nucleo"),
    sRaspCpu: $("s-rasp-cpu"),
    sRaspRam: $("s-rasp-ram"),
    statusViradas: $("status-viradas"),
    capturaFoto: $("captura-foto"),
    capturaVideo: $("captura-video"),
    capturaSequencia: $("captura-sequencia"),
    capturaIntervalo: $("captura-intervalo"),
    capturaQuantidade: $("captura-quantidade"),
    capturaStatus: $("captura-status"),
    capturaUltimo: $("captura-ultimo"),
    registroOperacao: $("registro-operacao"),
    copiarComandoPainel: $("copiar-comando-painel"),
    textoCopiarComando: $("texto-copiar-comando"),
    statusComandoPainel: $("status-comando-painel"),
  };

  const estado = { camera: null, processador: null, percepcao: null, sistema: {} };
  const histereseLinha = { anterior: null, contador: 0 };
  const metadados = new Map();
  let renderAgendado = false;
  let conectado = false;
  let ultimoEstadoRegistrado = "";

  /* ---------- Registro de operacao ---------- */

  function horarioAtual() {
    return new Intl.DateTimeFormat("pt-BR", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(new Date());
  }

  function registrarOperacao(texto, tipo = "info") {
    const registro = elementos.registroOperacao;
    if (!registro) return;
    const ultimo = registro.firstElementChild;
    if (ultimo?.dataset.texto === texto) return;

    const item = document.createElement("li");
    item.dataset.tipo = tipo;
    item.dataset.texto = texto;
    const horario = document.createElement("time");
    horario.textContent = horarioAtual();
    const mensagem = document.createElement("span");
    mensagem.textContent = texto;
    item.append(horario, mensagem);
    registro.prepend(item);
    while (registro.children.length > 45) registro.lastElementChild.remove();
  }

  /* ---------- Bola de estado do sistema ---------- */

  function definirEstadoSistema() {
    let situacao = "erro";
    if (conectado) {
      const idadeMs = estado.processador
        ? estado.processador.idade_ultimo_resultado_ms
        : estado.camera
          ? estado.camera.idade_ultimo_quadro_ms
          : null;
      const imagemViva =
        estado.camera &&
        estado.camera.saudavel &&
        idadeMs != null &&
        idadeMs <= 4000;
      situacao = imagemViva ? "ok" : "atencao";
    }
    elementos.pulso.dataset.estado = situacao;
    elementos.pulso.title =
      situacao === "ok"
        ? "tudo certo"
        : situacao === "atencao"
          ? "conectado, mas sem imagem saudável"
          : "sem conexão com o robô";
  }

  /* ---------- Laterais ---------- */

  function alternarLaterais(forcar) {
    const fechar =
      typeof forcar === "boolean"
        ? forcar
        : !document.body.classList.contains("laterais-fechadas");
    document.body.classList.toggle("laterais-fechadas", fechar);
    elementos.alternarLaterais.setAttribute("aria-expanded", String(!fechar));
    elementos.alternarLaterais.setAttribute(
      "aria-label",
      fechar ? "Mostrar barras laterais" : "Ocultar barras laterais",
    );
  }

  elementos.alternarLaterais.addEventListener("click", () => alternarLaterais());
  document.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape") alternarLaterais(true);
  });

  /* ---------- Cronometro ---------- */

  const cron = { rodando: false, inicio: 0, acumulado: 0, quadro: null };

  function cronTexto() {
    const totalMs = cron.acumulado + (cron.rodando ? performance.now() - cron.inicio : 0);
    const centesimos = Math.floor(totalMs / 10) % 100;
    const segundos = Math.floor(totalMs / 1000) % 60;
    const minutos = Math.floor(totalMs / 60000);
    return `${String(minutos).padStart(2, "0")}:${String(segundos).padStart(2, "0")}:${String(
      centesimos,
    ).padStart(2, "0")}`;
  }

  function cronPintar() {
    elementos.cronometro.textContent = cronTexto();
    if (cron.rodando) cron.quadro = requestAnimationFrame(cronPintar);
  }

  function cronAlternar() {
    if (cron.rodando) {
      cron.acumulado += performance.now() - cron.inicio;
      cron.rodando = false;
      cancelAnimationFrame(cron.quadro);
    } else {
      cron.inicio = performance.now();
      cron.rodando = true;
      cronPintar();
    }
    elementos.cronometro.dataset.rodando = String(cron.rodando);
  }

  function cronZerar() {
    cron.rodando = false;
    cron.acumulado = 0;
    cancelAnimationFrame(cron.quadro);
    elementos.cronometro.dataset.rodando = "false";
    cronPintar();
  }

  elementos.cronometro.addEventListener("click", cronAlternar);
  elementos.cronometro.addEventListener("dblclick", cronZerar);

  /* ---------- Renderizacao em lote ---------- */

  function agendarRender() {
    if (renderAgendado) return;
    renderAgendado = true;
    requestAnimationFrame(() => {
      renderAgendado = false;
      render();
    });
  }

  function definirTexto(elemento, texto) {
    if (elemento && elemento.textContent !== texto) elemento.textContent = texto;
  }

  function formatarDuracao(segundos) {
    if (!Number.isFinite(segundos) || segundos < 0) return "—";
    const minutos = Math.floor(segundos / 60);
    const resto = Math.floor(segundos % 60);
    return `${String(minutos).padStart(2, "0")}:${String(resto).padStart(2, "0")}`;
  }

  const MODOS_DEMO = [
    { texto: "SEGUINDO LINHA", cor: "linha", confianca: 0.98 },
    { texto: "VERDE · 180°", cor: "menta", confianca: 0.96 },
    { texto: "VERDE À ESQUERDA", cor: "verde", confianca: 0.94 },
    { texto: "VERDE À DIREITA", cor: "verde", confianca: 0.92 },
    { texto: "CURVA À ESQUERDA", cor: "ciano", confianca: 0.89 },
    { texto: "CURVA À DIREITA", cor: "laranja", confianca: 0.88 },
    { texto: "INTERSEÇÃO", cor: "violeta", confianca: 0.86 },
    { texto: "GAP", cor: "ambar", confianca: 0.78 },
    { texto: "RESGATE", cor: "lima", confianca: 0.8 },
    { texto: "PROCURANDO", cor: "rosa", confianca: 0.65 },
    { texto: "SEM LINHA", cor: "vermelho", confianca: 0.20 },
    { texto: "EM ESPERA", cor: "neutro", confianca: null },
  ];

  let indiceDemo = 0;
  setInterval(() => {
    indiceDemo = (indiceDemo + 1) % MODOS_DEMO.length;
    agendarRender();
  }, 2200);

  function estadoHero(percepcao) {
    if (!percepcao || !percepcao.estimativa) {
      return MODOS_DEMO[indiceDemo];
    }
    const e = percepcao.estimativa;
    const evento = String(e.evento ?? e.modo ?? "").toLowerCase();
    if (evento === "gap") {
      return { texto: "GAP", cor: "ambar", confianca: e.confianca };
    }
    if (evento === "resgate") {
      return { texto: "RESGATE", cor: "lima", confianca: e.confianca };
    }
    if (String(e.motivo ?? "").includes("intersecao")) {
      return { texto: "INTERSEÇÃO", cor: "violeta", confianca: e.confianca };
    }
    if (e.estado === "encontrada") {
      if (e.verde_esquerda && e.verde_direita) {
        return { texto: "VERDE · 180°", cor: "menta", confianca: e.confianca };
      }
      if (e.verde_esquerda) {
        return { texto: "VERDE À ESQUERDA", cor: "verde", confianca: e.confianca };
      }
      if (e.verde_direita) {
        return { texto: "VERDE À DIREITA", cor: "verde", confianca: e.confianca };
      }
      if (e.tipo_curva === "esquerda_suave" || e.tipo_curva === "esquerda_fechada") {
        return { texto: "CURVA À ESQUERDA", cor: "ciano", confianca: e.confianca };
      }
      if (e.tipo_curva === "direita_suave" || e.tipo_curva === "direita_fechada") {
        return { texto: "CURVA À DIREITA", cor: "laranja", confianca: e.confianca };
      }
      return { texto: "SEGUINDO LINHA", cor: "linha", confianca: e.confianca };
    }
    if (e.estado === "incerta") {
      return { texto: "PROCURANDO", cor: "rosa", confianca: e.confianca };
    }
    if (e.estado === "perdida") {
      return { texto: "SEM LINHA", cor: "vermelho", confianca: e.confianca };
    }
    return MODOS_DEMO[indiceDemo];
  }

  function render() {
    const { camera, processador, percepcao, sistema } = estado;

    definirEstadoSistema();

    definirTexto(
      elementos.fps,
      processador && processador.quadros_por_segundo
        ? processador.quadros_por_segundo.toFixed(1)
        : camera && camera.quadros_por_segundo_medido
          ? camera.quadros_por_segundo_medido.toFixed(1)
          : "—",
    );

    const idadeMs = processador
      ? processador.idade_ultimo_resultado_ms
      : camera
        ? camera.idade_ultimo_quadro_ms
        : null;
    definirTexto(elementos.quadro, idadeMs == null ? "—" : `${Math.round(idadeMs)} ms`);

    const totalMs = percepcao ? percepcao.latencia_total_ms : null;
    definirTexto(elementos.latencia, totalMs == null ? "—" : `${totalMs.toFixed(1)} ms`);

    /* Hero: O QUE ESTA ACONTECENDO */
    const heroi = estadoHero(percepcao);
    elementos.estadoDot.dataset.cor = heroi.cor;
    elementos.estadoTexto.dataset.cor = heroi.cor;
    definirTexto(elementos.estadoTexto, heroi.texto);
    definirTexto(
      elementos.estadoConfianca,
      heroi.confianca == null
        ? "confiança —"
        : `confiança ${Math.round(heroi.confianca * 100)}%`,
    );
    const chaveEstado = `${heroi.texto}:${heroi.cor}`;
    if (chaveEstado !== ultimoEstadoRegistrado) {
      ultimoEstadoRegistrado = chaveEstado;
      registrarOperacao(`Estado: ${heroi.texto}`, heroi.cor);
    }

    /* Aviso de imagem parada (idade da percepcao ou da camera). */
    const congelado = idadeMs == null || idadeMs > 4000;
    if (congelado) {
      elementos.avisoVideo.textContent = "imagem sem atualização recente";
      elementos.avisoVideo.classList.remove("oculto");
    } else {
      elementos.avisoVideo.classList.add("oculto");
    }

    if (elementos.placeholderPercepcao) {
      elementos.placeholderPercepcao.classList.toggle("oculto", Boolean(estado.modoPercepcao));
    }

    /* Insignia da linha com histerese (2 leituras). */
    let estadoLinhaBruto = "aguardando";
    if (percepcao && percepcao.estimativa) {
      const bruto = percepcao.estimativa.estado;
      estadoLinhaBruto =
        bruto === "encontrada" || bruto === "incerta" || bruto === "perdida"
          ? bruto
          : "aguardando";
    }
    if (estadoLinhaBruto !== histereseLinha.anterior) {
      histereseLinha.anterior = estadoLinhaBruto;
      histereseLinha.contador = 0;
    } else {
      histereseLinha.contador += 1;
    }
    if (elementos.bLinha && (histereseLinha.contador >= 2 || estadoLinhaBruto === "aguardando")) {
      elementos.bLinha.dataset.estado = estadoLinhaBruto;
    }

    const tipoCurva = percepcao && percepcao.estimativa ? percepcao.estimativa.tipo_curva : "";
    if (elementos.bEsquerda) {
      elementos.bEsquerda.dataset.ativo = tipoCurva.startsWith("esquerda") ? "true" : "false";
    }
    if (elementos.bDireita) {
      elementos.bDireita.dataset.ativo = tipoCurva.startsWith("direita") ? "true" : "false";
    }

    /* Estado do robo + sistema */
    definirTexto(
      elementos.sPercepcao,
      estado.modoPercepcao
        ? processador && processador.saudavel
          ? "neural · saudável"
          : "neural"
        : "indisponível",
    );
    definirTexto(
      elementos.sProcessados,
      processador ? `${processador.total_processados}` : "—",
    );
    if (camera) {
      definirTexto(elementos.sCamera, camera.nome_dispositivo || camera.origem || "—");
      definirTexto(elementos.sPerfil, camera.nome_perfil || "—");
      definirTexto(
        elementos.sResolucao,
        camera.largura ? `${camera.largura} × ${camera.altura}` : "—",
      );
      const cameraDisponivel = Boolean(camera.saudavel);
      const cameraEmAtencao = Boolean(camera.ativa) && !cameraDisponivel;
      definirTexto(
        elementos.sCam0Estado,
        cameraDisponivel ? "ok" : cameraEmAtencao ? "atenção" : "sem sinal",
      );
      elementos.sCam0Estado.dataset.estado = cameraDisponivel
        ? "ok"
        : cameraEmAtencao
          ? "atencao"
          : "erro";
      definirTexto(elementos.sCam0Fonte, camera.origem || camera.nome_dispositivo || "—");
      definirTexto(
        elementos.sCam0Video,
        camera.largura && camera.altura
          ? `${camera.largura} × ${camera.altura} · ${Math.round(camera.quadros_por_segundo_configurado || 0)} fps`
          : "—",
      );
    }
    definirTexto(elementos.sAtivo, formatarDuracao(sistema.tempo_ativo_s));
    definirTexto(
      elementos.sDisco,
      sistema.disco_livre_gb == null ? "—" : `${sistema.disco_livre_gb} GB`,
    );
    const raspberry = sistema.raspberry ?? {};
    const subtensao = raspberry.subtensao_atual;
    definirTexto(
      elementos.sRaspSubtensao,
      subtensao == null ? "sem leitura" : subtensao ? "detectada" : "não detectada",
    );
    elementos.sRaspSubtensao.dataset.estado =
      subtensao == null ? "aguardando" : subtensao ? "erro" : "ok";
    definirTexto(
      elementos.sRaspNucleo,
      raspberry.tensao_nucleo_v == null ? "—" : `${raspberry.tensao_nucleo_v.toFixed(2)} V`,
    );
    definirTexto(
      elementos.sRaspCpu,
      raspberry.temperatura_cpu_c == null ? "—" : `${raspberry.temperatura_cpu_c.toFixed(1)} °C`,
    );
    definirTexto(
      elementos.sRaspRam,
      raspberry.memoria_disponivel_mb == null ? "—" : `${raspberry.memoria_disponivel_mb} MB`,
    );

    renderCaptura();
  }

  /* ---------- Captura: foto, video e sequencia ---------- */

  function informarCaptura(texto, tipo) {
    elementos.capturaStatus.textContent = (texto || "pronto").toUpperCase();
    elementos.capturaStatus.dataset.tipo = tipo || "";
    const dot = $("captura-dot");
    if (dot) dot.dataset.tipo = tipo || "";
    if (texto && tipo !== "ativo") {
      clearTimeout(informarCaptura.temporizador);
      informarCaptura.temporizador = setTimeout(() => {
        elementos.capturaStatus.textContent = "PRONTO";
        elementos.capturaStatus.dataset.tipo = "";
        const d = $("captura-dot");
        if (d) d.dataset.tipo = "";
      }, 3000);
    }
  }

  function formatarCaminhoCaptura(caminho) {
    if (!caminho) return "";
    const partes = String(caminho).split(/[\\/]/);
    return partes.slice(-2).join("/");
  }

  function renderCaptura() {
    const captura = estado.captura;
    if (!captura) return;

    const videoAtivo = Boolean(captura.video_ativo);
    elementos.capturaVideo.dataset.ativo = String(videoAtivo);
    const sequenciaAtiva = Boolean(captura.sequencia_ativa);
    elementos.capturaSequencia.dataset.ativo = String(sequenciaAtiva);

    if (videoAtivo) {
      const duracao = captura.video_duracao_s == null ? "" : ` · ${captura.video_duracao_s}s`;
      informarCaptura(`gravando vídeo${duracao}`, "ativo");
    } else if (sequenciaAtiva) {
      const alvo = captura.sequencia_alvo > 0 ? `/${captura.sequencia_alvo}` : "";
      informarCaptura(
        `sequência · ${captura.sequencia_capturados}${alvo} frames`,
        "ativo",
      );
    }

    if (captura.ultimo_arquivo) {
      const exibivel = formatarCaminhoCaptura(captura.ultimo_arquivo);
      elementos.capturaUltimo.textContent = exibivel;
      elementos.capturaUltimo.title = captura.ultimo_arquivo;
    }
  }

  async function chamarCaptura(rota, corpo) {
    try {
      const resposta = await fetch(rota, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(corpo ?? {}),
      });
      return await resposta.json();
    } catch {
      return { ok: false, erro: "falha de rede" };
    }
  }

  elementos.capturaFoto.addEventListener("click", async () => {
    elementos.capturaFoto.dataset.ativo = "true";
    informarCaptura("salvando foto…", "ativo");
    const resposta = await chamarCaptura("/api/captura/foto");
    if (resposta.ok) {
      informarCaptura("foto salva", "ok");
      registrarOperacao("Captura: foto salva", "ok");
      if (resposta.arquivo) {
        const exibivel = formatarCaminhoCaptura(resposta.arquivo);
        elementos.capturaUltimo.textContent = exibivel;
        elementos.capturaUltimo.title = resposta.arquivo;
      }
    } else {
      informarCaptura(resposta.erro || "não foi possível salvar", "erro");
      registrarOperacao(resposta.erro || "Falha ao salvar foto", "erro");
    }
    setTimeout(() => {
      elementos.capturaFoto.dataset.ativo = "false";
    }, 700);
  });

  elementos.capturaVideo.addEventListener("click", async () => {
    const resposta = await chamarCaptura("/api/captura/video");
    if (resposta.ok) {
      const ativo = Boolean(resposta.video_ativo);
      elementos.capturaVideo.dataset.ativo = String(ativo);
      informarCaptura(resposta.mensagem || (ativo ? "gravando vídeo…" : "vídeo finalizado"), ativo ? "ativo" : "ok");
      registrarOperacao(ativo ? "Captura: vídeo iniciado" : "Captura: vídeo finalizado", ativo ? "ativo" : "ok");
      if (resposta.arquivo) {
        const exibivel = formatarCaminhoCaptura(resposta.arquivo);
        elementos.capturaUltimo.textContent = exibivel;
        elementos.capturaUltimo.title = resposta.arquivo;
      }
    } else {
      informarCaptura(resposta.erro || "falha no vídeo", "erro");
      registrarOperacao(resposta.erro || "Falha na gravação de vídeo", "erro");
    }
  });

  elementos.capturaSequencia.addEventListener("click", async () => {
    const intervalo = Number(elementos.capturaIntervalo.value) || 250;
    const quantidade = Number(elementos.capturaQuantidade.value) || 0;
    const resposta = await chamarCaptura("/api/captura/sequencia", {
      intervalo_ms: intervalo,
      maximo: quantidade,
    });
    if (resposta.ok) {
      const ativa = Boolean(resposta.sequencia_ativa);
      elementos.capturaSequencia.dataset.ativo = String(ativa);
      informarCaptura(resposta.mensagem || (ativa ? "sequência iniciada" : "sequência finalizada"), ativa ? "ativo" : "ok");
      registrarOperacao(ativa ? "Captura: sequência iniciada" : "Captura: sequência finalizada", ativa ? "ativo" : "ok");
    } else {
      informarCaptura(resposta.erro || "falha na sequência", "erro");
      registrarOperacao(resposta.erro || "Falha na sequência", "erro");
    }
  });

  /* ---------- Estado via SSE ---------- */

  function conectarEventos() {
    const fonte = new EventSource("/api/eventos");

    fonte.onopen = () => {
      conectado = true;
      registrarOperacao("Conexão SSE estabelecida", "ok");
      definirEstadoSistema();
    };
    fonte.onerror = () => {
      if (conectado) registrarOperacao("Conexão SSE interrompida", "erro");
      conectado = false;
      definirEstadoSistema();
    };

    fonte.onmessage = (mensagem) => {
      let dados;
      try {
        dados = JSON.parse(mensagem.data);
      } catch {
        return;
      }
      estado.camera = dados.camera ?? null;
      estado.processador = dados.processador ?? null;
      estado.percepcao = dados.percepcao ?? null;
      estado.sistema = dados.sistema ?? {};
      estado.captura = dados.captura ?? null;
      estado.modoPercepcao = Boolean(dados.modo_percepcao);
      definirEstadoSistema();
      agendarRender();
    };
  }

  /* ---------- Viradas: um cartao por grupo ---------- */

  function criarLinhaCampo(info) {
    const linha = document.createElement("div");
    linha.className = "linha-campo";

    const rotulo = document.createElement("label");
    rotulo.className = "campo-rotulo";
    rotulo.textContent = info.rotulo;
    rotulo.htmlFor = `campo-${info.chave}`;

    const diminuir = document.createElement("button");
    diminuir.type = "button";
    diminuir.className = "passo";
    diminuir.textContent = "−";
    diminuir.dataset.acao = "menos";
    diminuir.dataset.chave = info.chave;
    diminuir.setAttribute("aria-label", `Diminuir ${info.rotulo} (segure para acelerar)`);

    const campo = document.createElement("input");
    campo.type = "number";
    campo.className = "campo-valor mono";
    campo.id = `campo-${info.chave}`;
    campo.dataset.chave = info.chave;
    campo.min = info.minimo_ms;
    campo.max = info.maximo_ms;
    campo.step = info.passo_ms;
    campo.placeholder = "—";
    campo.setAttribute("aria-label", `${info.rotulo} em milissegundos`);
    if (info.valor_ms != null) campo.value = String(info.valor_ms);
    campo.addEventListener("focus", () => campo.select());

    const aumentar = document.createElement("button");
    aumentar.type = "button";
    aumentar.className = "passo";
    aumentar.textContent = "+";
    aumentar.dataset.acao = "mais";
    aumentar.dataset.chave = info.chave;
    aumentar.setAttribute("aria-label", `Aumentar ${info.rotulo} (segure para acelerar)`);

    const unidade = document.createElement("span");
    unidade.className = "unidade";
    unidade.textContent = "ms";

    linha.append(rotulo, diminuir, campo, aumentar, unidade);
    return linha;
  }

  async function carregarViradas() {
    let resposta;
    try {
      resposta = await fetch("/api/viradas", { cache: "no-store" });
    } catch {
      return;
    }
    if (!resposta.ok) return;
    const documento = await resposta.json();

    for (const grupo of documento.grupos) {
      const conteiner = document.querySelector(`[data-grupo-viradas="${grupo.id}"]`);
      if (!conteiner) continue;
      const fragmento = document.createDocumentFragment();
      for (const info of grupo.campos) {
        metadados.set(info.chave, info);
        fragmento.appendChild(criarLinhaCampo(info));
      }
      conteiner.replaceChildren(fragmento);
    }
  }

  function obterInput(chave) {
    return document.querySelector(`input.campo-valor[data-chave="${chave}"]`);
  }

  function definirValor(chave, valor) {
    const campo = obterInput(chave);
    if (campo) campo.value = valor === null || valor === undefined ? "" : String(valor);
  }

  function informarStatus(texto, tipo) {
    elementos.statusViradas.textContent = texto;
    elementos.statusViradas.dataset.tipo = tipo || "";
    if (texto) {
      clearTimeout(informarStatus.temporizador);
      informarStatus.temporizador = setTimeout(() => {
        elementos.statusViradas.textContent = "";
        elementos.statusViradas.dataset.tipo = "";
      }, 2600);
    }
  }

  async function enviarValor(chave, numero) {
    const campo = obterInput(chave);
    if (campo) campo.dataset.pendente = "true";

    try {
      const resposta = await fetch(`/api/viradas/${chave.replace(".", "/")}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ valor: numero }),
      });
      const documento = await resposta.json();
      if (documento.ok) {
        definirValor(chave, documento.valor_ms);
        informarStatus(`${documento.valor_ms} ms aplicado`, "ok");
        const meta = metadados.get(chave);
        if (meta) {
          meta.valor_ms = documento.valor_ms;
          registrarOperacao(`Ajuste: ${meta.rotulo} = ${documento.valor_ms} ms`, "ok");
        }
      } else {
        const meta = metadados.get(chave);
        if (meta) definirValor(chave, meta.valor_ms);
        informarStatus(documento.erro || "não foi possível aplicar", "erro");
        registrarOperacao(documento.erro || "Falha ao aplicar ajuste", "erro");
      }
    } catch {
      informarStatus("falha de rede; tente novamente", "erro");
      registrarOperacao("Falha de rede ao aplicar ajuste", "erro");
    } finally {
      if (campo) delete campo.dataset.pendente;
    }
  }

  const debounceEnvio = new Map();

  function enviarValorDebounced(chave, numero) {
    if (debounceEnvio.has(chave)) {
      clearTimeout(debounceEnvio.get(chave));
    }
    debounceEnvio.set(
      chave,
      setTimeout(() => {
        debounceEnvio.delete(chave);
        enviarValor(chave, numero);
      }, 70),
    );
  }

  function aplicarPasso(chave, direcao) {
    const meta = metadados.get(chave);
    if (!meta) return;
    const campo = obterInput(chave);
    const bruto = campo ? Number(campo.value) : NaN;
    const base =
      Number.isFinite(bruto) && campo && campo.value.trim() !== ""
        ? bruto
        : (meta.valor_ms ?? meta.minimo_ms ?? 0);
    const proximo = Math.min(
      meta.maximo_ms,
      Math.max(meta.minimo_ms, base + direcao * meta.passo_ms),
    );
    if (campo) campo.value = String(proximo);
    meta.valor_ms = proximo;
    enviarValorDebounced(chave, proximo);
  }

  /* Segurar acelera: 1 clique = 1 passo imediato; se segurar >360ms acelera a cada 70ms. */
  let timerAcelerar = null;
  let intervaloAcelerar = null;

  function pararAceleracao() {
    if (timerAcelerar) {
      clearTimeout(timerAcelerar);
      timerAcelerar = null;
    }
    if (intervaloAcelerar) {
      clearInterval(intervaloAcelerar);
      intervaloAcelerar = null;
    }
  }

  document.addEventListener("pointerdown", (evento) => {
    const alvo = evento.target.closest("[data-acao]");
    if (!alvo || evento.button !== 0) return;
    evento.preventDefault();
    const chave = alvo.dataset.chave;
    const direcao = alvo.dataset.acao === "mais" ? 1 : -1;

    aplicarPasso(chave, direcao);

    pararAceleracao();
    timerAcelerar = setTimeout(() => {
      intervaloAcelerar = setInterval(() => {
        aplicarPasso(chave, direcao);
      }, 70);
    }, 360);

    const aoFinalizar = () => {
      pararAceleracao();
      window.removeEventListener("pointerup", aoFinalizar);
      window.removeEventListener("pointercancel", aoFinalizar);
    };
    window.addEventListener("pointerup", aoFinalizar);
    window.addEventListener("pointercancel", aoFinalizar);
  });

  document.addEventListener("keydown", (evento) => {
    if (evento.key !== "ArrowUp" && evento.key !== "ArrowDown") return;
    const campo = evento.target.closest(".campo-valor");
    if (!campo) return;
    evento.preventDefault();
    aplicarPasso(campo.dataset.chave, evento.key === "ArrowUp" ? 1 : -1);
  });

  document.addEventListener("change", (evento) => {
    const campo = evento.target.closest(".campo-valor");
    if (!campo) return;
    const bruto = campo.value.trim();
    if (bruto === "") return;
    const numero = Number(bruto);
    if (!Number.isFinite(numero)) {
      const meta = metadados.get(campo.dataset.chave);
      if (meta) definirValor(campo.dataset.chave, meta.valor_ms);
      informarStatus("valor inválido", "erro");
      return;
    }
    enviarValor(campo.dataset.chave, numero);
  });

  /* ---------- Controle Manual (Motores e LEDs) ---------- */

  async function executarControle(acao, nomeExibicao, botao) {
    if (botao) {
      botao.dataset.ativo = "true";
      setTimeout(() => {
        botao.dataset.ativo = "false";
      }, 500);
    }
    informarStatus(`Comando: ${nomeExibicao}…`, "ok");
    try {
      const resposta = await fetch(`/api/controle/${acao}`, { method: "POST" });
      const doc = await resposta.json();
      if (doc.ok) {
        informarStatus(`${nomeExibicao} executado`, "ok");
        registrarOperacao(`Comando: ${nomeExibicao}`, "ok");
      } else {
        informarStatus(doc.erro || "falha no comando", "erro");
        registrarOperacao(doc.erro || `Falha no comando: ${nomeExibicao}`, "erro");
      }
    } catch {
      informarStatus(`${nomeExibicao} acionado`, "ok");
      registrarOperacao(`Comando solicitado: ${nomeExibicao}`, "info");
    }
  }

  function configurarControleManual() {
    const mapaBotoes = [
      { id: "ctrl-avancar", acao: "avancar", nome: "Avançar" },
      { id: "ctrl-parar", acao: "parar", nome: "Parar Motores" },
      { id: "ctrl-recuar", acao: "recuar", nome: "Recuar" },
      { id: "ctrl-led-on", acao: "led_on", nome: "LED Ligado" },
      { id: "ctrl-led-off", acao: "led_off", nome: "LED Desligado" },
    ];

    for (const item of mapaBotoes) {
      const btn = $(item.id);
      if (!btn) continue;
      btn.addEventListener("click", () => {
        executarControle(item.acao, item.nome, btn);
      });
    }
  }

  /* ---------- Toggle Camera Crua ---------- */

  function configurarToggleCameraCrua() {
    const btn = $("btn-toggle-crua");
    const badge = $("badge-crua");
    const visoes = $("conteiner-visoes");
    if (!btn || !badge || !visoes) return;

    let ativo = localStorage.getItem("painel_camera_crua") === "true";

    function atualizarUI() {
      btn.setAttribute("aria-pressed", String(ativo));
      visoes.dataset.crua = String(ativo);
      visoes.classList.toggle("modo-dupla", ativo);
      visoes.classList.toggle("modo-unica", !ativo);
      badge.textContent = ativo ? "ON" : "OFF";
    }

    btn.addEventListener("click", () => {
      ativo = !ativo;
      localStorage.setItem("painel_camera_crua", String(ativo));
      atualizarUI();
      registrarOperacao(ativo ? "Câmera crua exibida" : "Câmera crua ocultada", "info");
    });

    atualizarUI();
  }

  /* ---------- Comando de simulacao ---------- */

  function configurarCopiaComandoPainel() {
    const botao = elementos.copiarComandoPainel;
    const status = elementos.statusComandoPainel;
    if (!botao || !status) return;

    const comando =
      "C:\\Users\\Aluno\\.local\\bin\\uv.exe run obr-painel --simulacao --host 127.0.0.1 --porta 8090";
    botao.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(comando);
        status.textContent = "COMANDO COPIADO";
        registrarOperacao("Comando de simulação copiado", "ok");
        botao.dataset.estado = "copiado";
        definirTexto(elementos.textoCopiarComando, "Copiado");
      } catch {
        status.textContent = "NÃO FOI POSSÍVEL COPIAR";
        registrarOperacao("Não foi possível copiar o comando", "erro");
        botao.dataset.estado = "erro";
        definirTexto(elementos.textoCopiarComando, "Tentar de novo");
      }
      clearTimeout(configurarCopiaComandoPainel.temporizador);
      configurarCopiaComandoPainel.temporizador = setTimeout(() => {
        status.textContent = "";
        botao.dataset.estado = "";
        definirTexto(elementos.textoCopiarComando, "Copiar início");
      }, 2400);
    });
  }

  /* ---------- Reconexao de video ---------- */

  function vigiarVideo(img) {
    img.addEventListener("error", () => {
      setTimeout(() => {
        img.src = img.src;
      }, 1500);
    });
  }

  /* ---------- Inicializacao ---------- */

  async function iniciar() {
    registrarOperacao("Painel iniciado", "info");
    cronPintar();
    await carregarViradas();
    configurarControleManual();
    configurarToggleCameraCrua();
    configurarCopiaComandoPainel();
    vigiarVideo(elementos.video);
    vigiarVideo(elementos.videoCru);
    conectarEventos();
    agendarRender();
  }

  iniciar();
})();
