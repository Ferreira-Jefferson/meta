/* Painel /operacao: duas coisas que o servidor nao tem como fazer sozinho.
 *
 * 1. LEMBRAR O QUE ESTA ABERTO. Toda acao da pagina (atualizar caixa, iniciar,
 *    parar, marcar aviso como feito) responde trocando o `#ops-body` INTEIRO,
 *    e o servidor sempre renderiza o estado padrao. Sem isto, mexer no caixa
 *    de um robo fecharia todas as secoes -- o recolhivel viraria um estorvo em
 *    vez de uma ajuda. O estado e' do navegador de proposito: e' preferencia
 *    de visualizacao de quem olha, nao dado do sistema.
 *
 * 2. FILTRAR OS ATIVOS PELO ROBO ESCOLHIDO. O formulario de robo novo tem um
 *    <select> de robo e um de ativo; cada robo aceita a propria lista
 *    (`calibrated_setups`). O <select> de ativos carrega todas as opcoes com
 *    `data-robot`, e aqui se escondem as que nao sao do robo selecionado.
 *
 * Tudo por DELEGACAO no `document`: os nos sao recriados a cada swap do htmx,
 * entao ouvinte preso no elemento morreria no primeiro refresh de fundo.
 *
 * Degradacao sem JS: as secoes abrem/fecham normalmente (e' <details> nativo),
 * so' nao lembram entre acoes; e o select de ativos mostra os de todos os
 * robos -- o servidor recusa o par invalido com mensagem na tela.
 */
(function () {
  'use strict';

  var CHAVE = 'meta-operacao-abertos';
  var CHAVE_EXECUCAO = 'meta-operacao-execucao';

  // Generico: qualquer preferencia que so' existe no navegador (secao aberta,
  // modo de execucao escolhido) mora num mapa proprio dentro do localStorage,
  // chaveado pela CHAVE do mapa (nao confundir com a chave DENTRO do mapa,
  // que e' o slot/secao).
  function lidos(chave) {
    try { return JSON.parse(localStorage.getItem(chave)) || {}; }
    catch (e) { return {}; }   // modo privado, cota estourada, JSON corrompido
  }

  function grava(chave, mapa) {
    try { localStorage.setItem(chave, JSON.stringify(mapa)); } catch (e) {}
  }

  function restaura() {
    var mapa = lidos(CHAVE);
    var nodes = document.querySelectorAll('details[data-ops-key]');
    for (var i = 0; i < nodes.length; i++) {
      var d = nodes[i];
      var v = mapa[d.getAttribute('data-ops-key')];
      // `undefined` = o dono nunca mexeu nesta secao: respeita o default que o
      // servidor mandou (ha' casos em que ele ABRE de proposito -- aviso
      // pendente, credencial faltando, robo rodando).
      if (v === true || v === false) d.open = v;
    }
  }

  // `toggle` nao borbulha -> fase de CAPTURA, que pega eventos que nao sobem.
  document.addEventListener('toggle', function (ev) {
    var d = ev.target;
    if (!d || d.tagName !== 'DETAILS') return;
    var key = d.getAttribute('data-ops-key');
    if (!key) return;
    var mapa = lidos(CHAVE);
    mapa[key] = d.open;
    grava(CHAVE, mapa);
  }, true);

  function filtraAtivos(form) {
    var robo = form.querySelector('select[data-ops-robot-select]');
    var ativos = form.querySelector('select.ops-asset-select');
    if (!robo || !ativos) return;
    var escolhido = robo.value;
    var opts = ativos.querySelectorAll('option[data-robot]');
    for (var i = 0; i < opts.length; i++) {
      var o = opts[i];
      var meu = o.getAttribute('data-robot') === escolhido;
      o.hidden = !meu;
      // Ativo de outro robo tambem fica `disabled`: `hidden` sozinho ainda
      // permite selecionar por teclado em alguns navegadores.
      o.disabled = !meu || o.hasAttribute('data-em-uso');
    }
    // Trocar de robo invalida o ativo escolhido antes -- ele pode nem existir
    // na lista nova. Volta para o placeholder em vez de mandar um par que o
    // servidor recusaria.
    if (ativos.selectedOptions.length && ativos.selectedOptions[0].hidden) {
      ativos.value = '';
    }
  }

  document.addEventListener('change', function (ev) {
    var sel = ev.target;
    if (!sel || !sel.matches || !sel.matches('select[data-ops-robot-select]')) return;
    var form = sel.closest('form');
    if (form) filtraAtivos(form);
  });

  /* ---- campo de dinheiro: mascara + botao so quando ha o que salvar ------
   *
   * O campo era `type="number"`, que deixa digitar qualquer coisa e SO ENTAO
   * acusa ("os dois valores validos mais proximos sao 0,04 e 0,05"). Dinheiro
   * nao se digita assim: aqui cada digito entra pela DIREITA e o numero se
   * forma sozinho, com o centavo sempre em duas casas. Nao existe estado
   * invalido para acusar depois.
   */
  function centavos(texto) {
    var digitos = String(texto).replace(/\D/g, '');
    if (!digitos) return 0;
    // `slice(-15)`: o parseInt de uma cola gigantesca viraria imprecisao de
    // ponto flutuante silenciosa. 15 digitos = R$ 10 trilhoes, folga de sobra.
    return parseInt(digitos.slice(-15), 10);
  }

  function formataBRL(cent) {
    var s = String(cent);
    while (s.length < 3) s = '0' + s;                    // 7 -> "007" -> 0,07
    var reais = s.slice(0, -2), centavos_ = s.slice(-2);
    reais = reais.replace(/\B(?=(\d{3})+(?!\d))/g, '.'); // milhar
    return reais + ',' + centavos_;
  }

  document.addEventListener('input', function (ev) {
    var el = ev.target;
    if (!el || !el.matches || !el.matches('input[data-ops-money]')) return;
    el.value = formataBRL(centavos(el.value));
    // Cursor sempre no fim: os digitos entram pela direita, entao nao existe
    // "meio do numero" onde faria sentido deixa-lo.
    try { el.setSelectionRange(el.value.length, el.value.length); } catch (e) {}
  });

  // Cancelar (o "x"): `type="reset"` ja devolve o valor original sozinho, sem
  // JS. So falta tirar o foco -- senao o par de botoes continua na tela
  // depois de cancelar, sugerindo que ainda ha algo pendente.
  document.addEventListener('reset', function (ev) {
    var form = ev.target;
    if (!form || !form.classList || !form.classList.contains('ops-cash')) return;
    setTimeout(function () {
      var input = form.querySelector('input[data-ops-money]');
      if (input) input.blur();
    }, 0);
  });

  /* ---- caixa troca de saldo com a execução (pedido do dono, 2026-08-23) --
   *
   * "Sombra" e "Real" cada um tem o SEU saldo (`cash_sombra`/`cash`, ver
   * `AccountState.cash_for`). O `<select execution_mode>` e o `<input>` de
   * caixa sao FORMS IRMAOS (endpoints diferentes, ver a docstring de
   * `operacao_body.html`), entao mudar o select nao troca o valor do input
   * sozinho -- sem isto, o dono via "Sombra" selecionado mas continuava
   * editando (e submetendo) o caixa REAL, porque so' existe UM `<input>` na
   * tela e ele nao sabia de qual saldo era.
   *
   * So' troca o VALOR exibido/editavel, lido de `data-cash-live`/
   * `data-cash-sombra` (que o servidor ja mandou prontos, formatados) -- a
   * decisao de qual coluna GRAVAR continua so' do servidor
   * (`app.py::operacao_caixa`, a partir do `execution_mode` que o
   * `hx-include` do form de caixa manda junto).
   */
  function sincronizaCaixaComExecucao(select) {
    var sombra = select.value === 'shadow';
    var barra = select.closest('.ops-bar');
    if (barra) {
      var input = barra.querySelector('input[data-ops-money]');
      if (input) {
        var bruto = input.getAttribute(sombra ? 'data-cash-sombra' : 'data-cash-live');
        if (bruto != null) input.value = bruto;
      }
      var dica = barra.querySelector('[data-ops-cash-hint]');
      if (dica) dica.textContent = sombra ? 'sombra' : 'real';
    }
    // O resumo do cabeçalho (`ops-sum-<slot>`) mora FORA de `.ops-bar` --
    // dentro do `<summary>` do cartão, um nó irmão que não desce da mesma
    // raiz (ver `partials/operacao_resumo.html`). O id do `<select>` é
    // `ops-exec-<slot>` (ver `operacao_slot_control.html`); o do resumo e'
    // `ops-sum-<slot>` -- mesmo sufixo, prefixo diferente.
    var slotId = slotDoSelectExecucao(select);
    if (!slotId) return;
    var resumo = document.getElementById('ops-sum-' + slotId);
    if (!resumo) return;
    var cash = resumo.querySelector('.ops-sum-cash');
    if (cash) {
      var valor = cash.getAttribute(sombra ? 'data-cash-sombra' : 'data-cash-live');
      if (valor != null) cash.textContent = 'R$ ' + valor;
    }
    var hint = resumo.querySelector('.ops-sum-hint');
    if (hint) {
      var ok = hint.getAttribute(sombra ? 'data-ok-sombra' : 'data-ok-live');
      if (ok != null) hint.classList.toggle('is-blocked', ok === '0');
    }
    // Cartões de capital (`partials/operacao_slot_live.html`): "Caixa",
    // "Carteira" e "Patrimônio" trocam de valor junto (TODOS os que derivam
    // do caixa, não só o primeiro -- reclamação do dono, 2026-08-23: a
    // primeira versão desta função só cobria o card "Caixa"). "Resultado"
    // NÃO troca -- é `machine.session_pnl`, o mesmo número nos dois modos
    // (a máquina processa fill real e simulado do mesmo jeito), então o
    // card nem carrega `data-cash-*`. As duas visões mostram os MESMOS
    // cards agora (pedido do dono, 2026-08-23) -- não sobrou nenhum
    // exclusivo de um modo pra esconder/mostrar.
    var cartoes = document.getElementById('ops-cards-' + slotId);
    if (!cartoes) return;
    var valores = cartoes.querySelectorAll('.v[data-cash-live]');
    for (var j = 0; j < valores.length; j++) {
      var v = valores[j].getAttribute(sombra ? 'data-cash-sombra' : 'data-cash-live');
      if (v != null) valores[j].textContent = 'R$ ' + v;
    }
  }

  // Extrai o slot a partir do id `ops-exec-<slot>` (formato fixado em
  // `operacao_slot_control.html`); `null` se o elemento nao seguir o padrao.
  function slotDoSelectExecucao(sel) {
    if (!sel.id || sel.id.indexOf('ops-exec-') !== 0) return null;
    return sel.id.slice('ops-exec-'.length);
  }

  document.addEventListener('change', function (ev) {
    var sel = ev.target;
    if (!sel || !sel.matches || !sel.matches('select[name="execution_mode"]')) return;
    sincronizaCaixaComExecucao(sel);
    // Escolha do dono, nao so' o que a conta rodou da ultima vez: sem isto,
    // atualizar a pagina com "Real" escolhido (mas ainda nao iniciado) volta
    // pro default "Sombra" do servidor -- mesma queixa de 2026-08-23 ("todo
    // recarregar de tela nao guarda o ultimo estado"), agora no select em vez
    // do <details>. Ver `restauraExecucao`.
    var slotId = slotDoSelectExecucao(sel);
    if (!slotId) return;
    var mapa = lidos(CHAVE_EXECUCAO);
    mapa[slotId] = sel.value;
    grava(CHAVE_EXECUCAO, mapa);
  });

  // Reaplica a escolha salva por cima do default que o servidor renderizou
  // (`config_anterior.execution_mode`, o modo da ULTIMA PARTIDA DE VERDADE --
  // nao serve pra lembrar uma escolha que o dono fez e ainda nem iniciou).
  // Roda em toda troca de `#ops-body`/refresh de fundo, entao tambem cobre a
  // barra reaparecendo depois que o robo para.
  function restauraExecucao() {
    var mapa = lidos(CHAVE_EXECUCAO);
    var selects = document.querySelectorAll('select[name="execution_mode"]');
    for (var i = 0; i < selects.length; i++) {
      var sel = selects[i];
      var slotId = slotDoSelectExecucao(sel);
      if (!slotId) continue;
      var salvo = mapa[slotId];
      if (salvo !== 'shadow' && salvo !== 'live') continue;   // nunca mexeu
      if (sel.value === salvo) continue;
      sel.value = salvo;
      sincronizaCaixaComExecucao(sel);   // caixa/cartoes/resumo tem que seguir
    }
  }

  function aplica() {
    restaura();
    restauraExecucao();
    var forms = document.querySelectorAll('form.ops-new-robot-form');
    for (var i = 0; i < forms.length; i++) filtraAtivos(forms[i]);
  }

  // `htmx:afterSwap` cobre tanto a troca do `#ops-body` inteiro quanto o
  // refresh de fundo de um cartao.
  document.addEventListener('htmx:afterSwap', aplica);
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', aplica);
  } else {
    aplica();
  }
})();
