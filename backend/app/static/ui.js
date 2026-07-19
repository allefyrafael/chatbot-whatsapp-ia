/* Retorno visual do painel: aviso flutuante, confirmação e carregamento.
 *
 * Existe porque várias telas mudavam de página sem dizer nada: o aluno clicava, era
 * redirecionado e não sabia se tinha dado certo, se ainda estava processando ou se
 * falhou. Tudo passa por aqui para o comportamento ser o mesmo em todo o painel.
 *
 * API (window.UI):
 *   UI.aviso(texto, tipo)          tipo: 'ok' | 'erro' | 'info'
 *   UI.confirmar({...}) -> Promise<bool>
 *   UI.carregando(botao, texto)    devolve funcao que restaura o botao
 *   UI.enviar(form, {...})         POST por fetch com carregamento + aviso + destino
 */
(function () {
    "use strict";

    var ICONES = {
        ok: '<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M8.2 13.6 5 10.4l1.2-1.2 2 2 5.6-5.6L15 6.8z"/></svg>',
        erro: '<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M10 2a8 8 0 100 16 8 8 0 000-16zm1 12H9v-2h2zm0-3H9V6h2z"/></svg>',
        info: '<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M10 2a8 8 0 100 16 8 8 0 000-16zm1 4H9v2h2zm0 3H9v5h2z"/></svg>'
    };

    function pilha() {
        var el = document.getElementById("ui-avisos");
        if (!el) {
            el = document.createElement("div");
            el.id = "ui-avisos";
            el.className = "ui-avisos";
            el.setAttribute("role", "status");
            el.setAttribute("aria-live", "polite");
            document.body.appendChild(el);
        }
        return el;
    }

    function aviso(texto, tipo, duracaoMs) {
        tipo = tipo || "info";
        var caixa = document.createElement("div");
        caixa.className = "ui-aviso ui-aviso--" + tipo;
        caixa.innerHTML =
            '<span class="ui-aviso-icone">' + (ICONES[tipo] || ICONES.info) + "</span>" +
            '<div class="ui-aviso-texto">' + texto + "</div>" +
            '<button type="button" class="ui-aviso-fechar" aria-label="Fechar">&times;</button>';
        pilha().appendChild(caixa);

        function sair() {
            caixa.classList.add("ui-aviso--saindo");
            setTimeout(function () { caixa.remove(); }, 200);
        }
        caixa.querySelector(".ui-aviso-fechar").addEventListener("click", sair);
        // Erro fica até o usuário fechar: costuma exigir uma ação dele.
        var vida = duracaoMs != null ? duracaoMs : (tipo === "erro" ? 0 : 4500);
        if (vida > 0) setTimeout(sair, vida);
        return caixa;
    }

    /* Confirmação estilizada. Substitui o confirm() do navegador, que alguns navegadores
       escondem e que não deixa destacar a gravidade da ação. */
    function confirmar(opcoes) {
        opcoes = opcoes || {};
        return new Promise(function (resolve) {
            var fundo = document.createElement("div");
            fundo.className = "modal-fundo";
            fundo.innerHTML =
                '<div class="modal-caixa" role="dialog" aria-modal="true">' +
                    '<div class="modal-icone">' + (opcoes.icone || "⚠️") + "</div>" +
                    "<h3>" + (opcoes.titulo || "Confirmar") + "</h3>" +
                    '<p class="modal-msg">' + (opcoes.texto || "") + "</p>" +
                    '<div class="ui-modal-acoes">' +
                        '<button type="button" class="btn btn-ghost" data-nao>' +
                            (opcoes.cancelar || "Cancelar") + "</button>" +
                        '<button type="button" class="btn ' + (opcoes.perigo ? "btn-danger" : "btn-primary") +
                            '" data-sim>' + (opcoes.confirmar || "Confirmar") + "</button>" +
                    "</div>" +
                "</div>";
            document.body.appendChild(fundo);

            function fechar(resposta) {
                fundo.remove();
                document.removeEventListener("keydown", aoTeclar);
                resolve(resposta);
            }
            function aoTeclar(e) { if (e.key === "Escape") fechar(false); }

            fundo.querySelector("[data-sim]").addEventListener("click", function () { fechar(true); });
            fundo.querySelector("[data-nao]").addEventListener("click", function () { fechar(false); });
            fundo.addEventListener("click", function (e) { if (e.target === fundo) fechar(false); });
            document.addEventListener("keydown", aoTeclar);
            fundo.querySelector("[data-sim]").focus();
        });
    }

    /* Botão em estado de carregamento. Devolve a função que desfaz. */
    function carregando(botao, texto) {
        if (!botao) return function () {};
        var original = botao.innerHTML;
        botao.disabled = true;
        botao.classList.add("btn--carregando");
        botao.innerHTML = '<span class="ui-spinner" aria-hidden="true"></span>' +
                          (texto || "Aguarde…");
        return function () {
            botao.disabled = false;
            botao.classList.remove("btn--carregando");
            botao.innerHTML = original;
        };
    }

    /* Envia um <form> por fetch, mostrando carregamento e o resultado.
       O servidor responde JSON ({ok, erro, destino}) quando vê o cabeçalho abaixo. */
    function enviar(form, opcoes) {
        opcoes = opcoes || {};
        var botao = opcoes.botao || form.querySelector('button[type="submit"]');
        var restaurar = carregando(botao, opcoes.carregando);

        return fetch(form.action, {
            method: (form.method || "post").toUpperCase(),
            headers: { "X-Requested-With": "fetch" },
            body: new FormData(form)
        })
            .then(function (r) { return r.json().catch(function () { return {ok: r.ok}; }); })
            .then(function (d) {
                if (d.ok) {
                    aviso(d.mensagem || opcoes.sucesso || "Pronto!", "ok");
                    var destino = d.destino || opcoes.destino;
                    // Deixa o aviso visível por um instante antes de trocar de tela.
                    if (destino) setTimeout(function () { window.location.href = destino; }, 900);
                    else restaurar();
                } else {
                    restaurar();
                    aviso(d.erro || opcoes.erro || "Não consegui concluir.", "erro");
                }
                return d;
            })
            .catch(function () {
                restaurar();
                aviso(
                    "Não consegui falar com o servidor. Verifique se a janela do " +
                    "<code>run.bat</code> ainda está aberta.", "erro"
                );
            });
    }

    /* Qualquer form com data-confirmar pede confirmação antes de enviar.
       Ex.: <form data-confirmar="Apagar tudo?" data-perigo="1"> */
    document.addEventListener("submit", function (e) {
        var form = e.target;
        var pergunta = form.getAttribute("data-confirmar");
        if (!pergunta || form.dataset.confirmado === "1") return;

        e.preventDefault();
        confirmar({
            titulo: form.getAttribute("data-confirmar-titulo") || "Tem certeza?",
            texto: pergunta,
            confirmar: form.getAttribute("data-confirmar-ok") || "Sim, continuar",
            perigo: form.hasAttribute("data-perigo")
        }).then(function (sim) {
            if (!sim) return;
            form.dataset.confirmado = "1";
            var botao = form.querySelector('button[type="submit"]');
            carregando(botao, form.getAttribute("data-carregando") || "Processando…");
            form.submit();
        });
    }, true);

    /* Mesmo recurso no BOTÃO, para casos em que o form é compartilhado e a ação depende
       do botão clicado (`formaction`) — confirmar no form pediria confirmação até para
       salvar. Ex.: "Salvar" e "Excluir" dentro do mesmo <form> do RAG. */
    document.addEventListener("click", function (e) {
        var botao = e.target.closest ? e.target.closest("button[data-confirmar]") : null;
        if (!botao || botao.dataset.confirmado === "1") return;

        e.preventDefault();
        e.stopPropagation();
        confirmar({
            titulo: botao.getAttribute("data-confirmar-titulo") || "Tem certeza?",
            texto: botao.getAttribute("data-confirmar"),
            confirmar: botao.getAttribute("data-confirmar-ok") || "Sim, excluir",
            perigo: botao.hasAttribute("data-perigo")
        }).then(function (sim) {
            if (!sim) return;
            botao.dataset.confirmado = "1";
            botao.click();
        });
    }, true);

    window.UI = { aviso: aviso, confirmar: confirmar, carregando: carregando, enviar: enviar };
})();
