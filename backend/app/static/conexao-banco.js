/* Janela flutuante da conexão com o banco — usada pelo assistente inicial e pela tela
   de Configurações.

   Por que fetch em vez do envio normal do formulário: testar um RDS leva alguns segundos
   e, recarregando a página, o aluno fica sem nenhum sinal de que algo está acontecendo.
   Aqui a mesma janela mostra os três estados (conectando / sucesso / erro), e os avisos
   em bloco no topo da página deixam de existir.

   Sem JavaScript o formulário é enviado normalmente e o servidor responde HTML. */
(function () {
    var form = document.getElementById("form-banco");
    if (!form) return;

    var botao = document.getElementById("btn-testar");
    var rotuloBotao = botao.textContent;
    var modal = document.getElementById("modal");
    var corpo = document.getElementById("modal-corpo");
    var destino = form.getAttribute("data-destino") || "/";

    function abrir(html) {
        corpo.innerHTML = html;
        modal.hidden = false;
    }

    function fechar() {
        modal.hidden = true;
        botao.disabled = false;
        botao.textContent = rotuloBotao;
    }

    function mostrarConectando(host) {
        abrir(
            '<div class="conectando">' +
                '<div class="plug-cena">' +
                    '<span class="plug">🔌</span><span class="faisca">⚡</span><span>🗄️</span>' +
                '</div>' +
                '<h3 id="modal-titulo">Conectando ao seu banco…</h3>' +
                '<p class="modal-msg" style="text-align:center">' +
                    'Estamos falando com <b>' + host + '</b> na AWS.<br>' +
                    'Isso costuma levar alguns segundos.' +
                '</p>' +
            '</div>'
        );
    }

    function mostrarSucesso(dados) {
        abrir(
            '<div class="modal-icone">✅</div>' +
            '<h3 id="modal-titulo">Conectado com sucesso!</h3>' +
            '<p class="modal-msg" style="text-align:center">' +
                'O chatbot já está ligado ao banco <b>' + (dados.banco || "") + '</b>.' +
            '</p>' +
            '<button type="button" class="btn btn-primary btn-lg" id="modal-ok">OK, continuar</button>'
        );
        document.getElementById("modal-ok").addEventListener("click", function () {
            window.location.href = dados.destino || destino;
        });
    }

    function mostrarErro(mensagem) {
        abrir(
            '<div class="modal-icone">⚠️</div>' +
            '<h3 id="modal-titulo">Não foi possível conectar</h3>' +
            '<p class="modal-msg">' + mensagem + '</p>' +
            '<button type="button" class="btn btn-primary" id="modal-fechar">Entendi, vou corrigir</button>'
        );
        document.getElementById("modal-fechar").addEventListener("click", fechar);
    }

    // Erro vindo de um envio sem JavaScript: mostra na janela em vez de um bloco no topo.
    var erroDoServidor = (window.ERRO_DO_SERVIDOR || "").trim();
    if (erroDoServidor) mostrarErro(erroDoServidor);

    form.addEventListener("submit", function (evento) {
        evento.preventDefault();
        botao.disabled = true;
        botao.textContent = "Testando conexão…";
        mostrarConectando(form.host.value.trim() || "seu servidor");

        fetch(form.action, {
            method: "POST",
            headers: { "X-Requested-With": "fetch" },
            body: new FormData(form)
        })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (d.ok) mostrarSucesso(d);
                else mostrarErro(d.erro || "Erro desconhecido.");
            })
            .catch(function () {
                mostrarErro(
                    "Não consegui falar com o servidor do painel. Verifique se a janela do " +
                    "<code>run.bat</code> ainda está aberta e tente de novo."
                );
            });
    });
})();
