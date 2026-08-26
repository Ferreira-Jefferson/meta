/* Painel /operacao: duas coisas que o servidor nao tem como fazer sozinho.
 *
 * 1. LEMBRAR O QUE ESTA ABERTO. Toda acao da pagina (atualizar caixa, iniciar,
 *    parar, marcar aviso como feito) responde trocando o `#ops-body` INTEIRO,
 *    e o servidor sempre renderiza o estado padrao. Sem isto, mexer no caixa
 *    de um robo fecharia todas as secoes -- o recolhivel viraria um estorvo em
 *    vez de uma ajuda. O estado e' do navegador de proposito: e' preferencia
 *    de visualizacao de quem olha, nao dado do sistema.
 *
 * 2. FILTRAR OS ATIVOS PELO ROBO+MODO ESCOLHIDOS. O formulario de robo novo
 *    pede Robo e Modo ANTES do Ativo (pedido do dono, 2026-08-25 -- ver
 *    `atualizaAtivos`): o <select> de ativos carrega todas as opcoes com
 *    `data-robot`/`data-modos-usados`, e aqui se escondem as que nao sao do
 *    robo selecionado e se desabilitam as que o (robo, ativo, modo) ja
 *    escolhido tornaria um trio duplicado.
 *
 * 3. REVELAR A CAIXA "RESTAURAR" so' no trio que tem historico guardado
 *    (pedido do dono, 2026-08-26 -- ver `atualizaRestauro`): o mesmo
 *    <select> de ativos carrega `data-modos-arquivados`, e a caixa some
 *    quando o (robo, ativo, modo) escolhido nao e' um deles.
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

  // Modo vem PRIMEIRO no formulario, antes de Robo e de Ativo (pedido do
  // dono, 2026-08-25: a ordem antiga -- Robo, Ativo, Modo -- fazia escolher
  // um ativo com so' um modo em uso EMPURRAR o Modo sozinho pro outro valor
  // por baixo dos panos, o que confundia mais do que ajudava: o dono clicava
  // num ativo marcado "parado" esperando continuar naquele modo e via o
  // Modo pular sozinho pra "Real"). Com o Modo escolhido PRIMEIRO, ele nunca
  // muda por causa do Robo ou do Ativo -- sao Robo e Ativo que se ajustam ao
  // Modo ja escolhido: o trio que ja existe fica so' DESABILITADO (nao
  // escondido, pra nao sumir a bolinha/status que explica o motivo), e o
  // dono troca o Modo se quiser aquele ativo mesmo assim.
  function atualizaAtivos(form) {
    var robo = form.querySelector('select[data-ops-robot-select]');
    var modo = form.querySelector('select[data-ops-mode-select]');
    var ativos = form.querySelector('select.ops-asset-select');
    var submit = form.querySelector('[data-ops-submit]');
    if (!robo || !modo || !ativos) return;
    var escolhidoRobo = robo.value;
    var escolhidoModo = modo.value;
    var opts = ativos.querySelectorAll('option[data-robot]');
    var livre = false;
    for (var i = 0; i < opts.length; i++) {
      var o = opts[i];
      var meu = o.getAttribute('data-robot') === escolhidoRobo;
      o.hidden = !meu;
      var label = o.getAttribute('data-label');
      var usados = ((o.getAttribute('data-modos-usados')) || '').split(',').filter(Boolean);
      var rodando = ((o.getAttribute('data-modos-rodando')) || '').split(',').filter(Boolean);
      // "Existe" e' sempre relativo ao Modo JA escolhido -- nao ao ativo
      // sozinho: PMAM3 com so' a sombra criada aparece livre quando o Modo e'
      // Real, e so' vira "parado"/desabilitado quando o Modo e'
      // Simulacao (o trio que o servidor recusaria).
      var existe = usados.indexOf(escolhidoModo) !== -1;
      var operando = rodando.indexOf(escolhidoModo) !== -1;
      if (label) {
        var sufixo = operando ? ' · operando' : (existe ? ' · parado' : '');
        o.textContent = (existe ? '●' : '○') + ' ' + label + sufixo;
      }
      o.classList.remove('is-running', 'is-idle');
      if (operando) o.classList.add('is-running');
      else if (existe) o.classList.add('is-idle');
      // Ativo de outro robo, ou trio (robo, ativo, modo) ja existente:
      // `disabled`. `hidden` sozinho ainda permite selecionar por teclado em
      // alguns navegadores, e aqui o trio existente PRECISA continuar
      // visivel (so' desabilitado) pro dono entender o motivo pela bolinha.
      o.disabled = !meu || existe;
      if (meu && !o.disabled) livre = true;
    }
    // Trocar de robo ou de modo pode invalidar o ativo ja escolhido (virou
    // trio duplicado, ou nem pertence mais a este robo). Volta pro
    // placeholder em vez de deixar selecionado um valor agora bloqueado.
    var sel = ativos.selectedOptions[0];
    if (sel && (sel.hidden || sel.disabled)) ativos.value = '';
    // Nenhum ativo livre para este (robo, modo): nao ha nada valido para
    // submeter -- desabilita o botao em vez de deixar o clique estourar no
    // servidor.
    if (submit) submit.disabled = !livre;
    atualizaRestauro(form);
  }

  /* Caixa "restaurar o historico guardado" (pedido do dono, 2026-08-26).
   *
   * Aparece SO' quando o trio (robo, ativo, modo) escolhido agora tem
   * historico guardado -- um robo que foi removido com "guardar". Fora
   * disso, seria um controle marcado oferecendo restaurar o nada.
   *
   * Volta MARCADA toda vez que reaparece, mesmo que o dono tenha desmarcado
   * num trio anterior: "quero comecar do zero" e' uma decisao sobre AQUELE
   * arquivo, nao uma preferencia que deva seguir o dono pro proximo robo --
   * e o efeito dela (descartar o historico) nao tem volta.
   */
  function atualizaRestauro(form) {
    var campo = form.querySelector('[data-ops-restore-field]');
    if (!campo) return;                       // nenhum arquivo: nem renderizado
    var modo = form.querySelector('select[data-ops-mode-select]');
    var ativos = form.querySelector('select.ops-asset-select');
    var sel = ativos && ativos.selectedOptions[0];
    var guardados = sel
      ? ((sel.getAttribute('data-modos-arquivados') || '').split(',').filter(Boolean))
      : [];
    var tem = !!modo && guardados.indexOf(modo.value) !== -1;
    campo.hidden = !tem;
    var check = form.querySelector('[data-ops-restore-input]');
    if (check && !tem) check.checked = true;
  }

  document.addEventListener('change', function (ev) {
    var sel = ev.target;
    if (!sel || !sel.matches || !sel.matches('select.ops-asset-select')) return;
    var form = sel.closest('form');
    if (form) atualizaRestauro(form);
  });

  document.addEventListener('change', function (ev) {
    var sel = ev.target;
    if (!sel || !sel.matches) return;
    if (sel.matches('select[data-ops-robot-select]') || sel.matches('select[data-ops-mode-select]')) {
      var form = sel.closest('form');
      if (form) atualizaAtivos(form);
    }
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

  /* ---- arrastar um robo de day trade pra reordenar (pedido do dono, 2026-
   * 08-24) -----------------------------------------------------------------
   *
   * Drag-and-drop nativo do navegador (`draggable="true"` no cabo dentro do
   * `<summary>`, ver `partials/operacao_body.html`), nao uma lib de terceiro:
   * o painel inteiro ja e' HTML simples + htmx, e o navegador ja da o
   * feedback visual do arrasto (ghost) de graca.
   *
   * O reposicionamento em si acontece durante o proprio `dragover`, movendo
   * o NO do cartao no DOM (`insertBefore`) conforme o mouse passa da metade
   * de cima pra metade de baixo do cartao sob o cursor -- e' o que da a
   * sensacao de arrastar pra "qualquer posicao", nao so trocar com o vizinho.
   * So' no `dragend` e' que a ordem final (lida do DOM) e' mandada pro
   * servidor -- gravar a cada `dragover` faria um POST por pixel arrastado.
   */
  var arrastando = null;

  function cartoesDayTrade() {
    return Array.prototype.slice.call(
      document.querySelectorAll('.ops-slot.ops-robot[data-ops-slot-id]')
    );
  }

  document.addEventListener('dragstart', function (ev) {
    var cabo = ev.target.closest('[data-ops-drag-handle]');
    if (!cabo) return;
    var artigo = cabo.closest('.ops-slot.ops-robot[data-ops-slot-id]');
    if (!artigo) return;
    arrastando = artigo;
    artigo.classList.add('is-dragging');
    ev.dataTransfer.effectAllowed = 'move';
    // `setData` vazio: alguns navegadores exigem que ALGO seja gravado para
    // o arrasto ser aceito, mas o dado que importa e' lido do DOM no fim
    // (`dragend`), nao daqui.
    try { ev.dataTransfer.setData('text/plain', artigo.getAttribute('data-ops-slot-id') || ''); }
    catch (e) {}
  });

  document.addEventListener('dragover', function (ev) {
    if (!arrastando) return;
    var sobre = ev.target.closest('.ops-slot.ops-robot[data-ops-slot-id]');
    if (!sobre || sobre === arrastando) return;
    ev.preventDefault();  // obrigatorio: sem isto o navegador recusa o drop
    var caixa = sobre.getBoundingClientRect();
    var depoisDoMeio = (ev.clientY - caixa.top) > caixa.height / 2;
    sobre.parentNode.insertBefore(arrastando, depoisDoMeio ? sobre.nextSibling : sobre);
  });

  document.addEventListener('dragend', function () {
    if (!arrastando) return;
    arrastando.classList.remove('is-dragging');
    var ids = cartoesDayTrade().map(function (a) { return a.getAttribute('data-ops-slot-id'); });
    arrastando = null;
    if (window.htmx) {
      htmx.ajax('POST', '/operacao/daytrade/reordenar', {
        target: '#ops-body', swap: 'outerHTML',
        values: { ordem: ids.join(',') },
      });
    }
  });

  /* ---- card de colisão de símbolo (pedido do dono, 2026-08-25) -----------
   *
   * `<dialog>` nativo (`partials/operacao_colisao.html`) só nasce ABERTO de
   * verdade com `showModal()` -- o atributo `open` sozinho não centraliza
   * nem cobre o fundo. Abre so' UMA vez: `data-ops-modal-shown` marca que
   * este NO especifico ja foi tratado, senao o poll de fundo de um cartao
   * QUALQUER (afterSwap dispara pra qualquer swap, nao so' o do dialogo)
   * reabriria um modal que o dono acabou de fechar -- o dialogo continua no
   * DOM ate o proximo swap de `#ops-body` INTEIRO (outro clique em
   * "Iniciar", ou o proprio botao "Parar" de dentro dele).
   */
  function abreColisao() {
    var dlg = document.querySelector('dialog[data-ops-modal]:not([data-ops-modal-shown])');
    if (!dlg) return;
    dlg.setAttribute('data-ops-modal-shown', '1');
    if (typeof dlg.showModal === 'function') {
      try { dlg.showModal(); } catch (e) {}
    }
  }

  // Clique no backdrop fecha (pedido implicito de todo modal): so' o clique
  // no proprio <dialog> conta como backdrop -- um clique dentro do conteudo
  // borbulha ate o <dialog> tambem, entao confere se o ponto clicado cai
  // FORA do retangulo do conteudo antes de fechar.
  document.addEventListener('click', function (ev) {
    var dlg = ev.target;
    if (!dlg || dlg.tagName !== 'DIALOG' || !dlg.hasAttribute('data-ops-modal') || !dlg.open) return;
    var r = dlg.getBoundingClientRect();
    var dentro = ev.clientX >= r.left && ev.clientX <= r.right
              && ev.clientY >= r.top && ev.clientY <= r.bottom;
    if (!dentro) dlg.close();
  });

  function aplica() {
    restaura();
    var forms = document.querySelectorAll('form.ops-new-robot-form');
    for (var i = 0; i < forms.length; i++) atualizaAtivos(forms[i]);
    abreColisao();
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
