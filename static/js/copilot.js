/**
 * ROTATOR COPILOT - Intelligence Artificielle intégrée
 */
(function () {
    const COPILOT_HTML = `
    <div id="rotator-copilot-container">
      <div class="cp-trigger" id="cpTrigger">
        <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
        </svg>
      </div>
      <div class="cp-window" id="cpWindow">
        <div class="cp-header">
          <div class="cp-title">
            <svg style="width:20px" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            <span>Rotator Copilot</span>
          </div>
          <div class="cp-close" id="cpClose">
            <svg style="width:18px" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
        </div>
        <div class="cp-messages" id="cpMessages">
          <div class="cp-msg bot">Bonjour ! Je suis votre Copilot. Je peux vous aider à configurer le Rotator ou gérer vos projets. Que puis-je faire pour vous ?</div>
        </div>
        <div class="cp-input-area">
          <div class="cp-input-container">
            <input type="text" class="cp-input" id="cpInput" placeholder="Posez-moi une question..." />
            <button class="cp-send" id="cpSend" title="Envoyer">
               <svg style="width:18px" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  `;

    let history = [];
    let isThinking = false;

    function init() {
        // Check if already exists
        if (document.getElementById('rotator-copilot-container')) return;

        // Append styles if not already there
        if (!document.querySelector('link[href*="copilot.css"]')) {
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = '/static/css/copilot.css';
            document.head.appendChild(link);
        }

        // Append widget
        const div = document.createElement('div');
        div.innerHTML = COPILOT_HTML;
        document.body.appendChild(div.firstElementChild);

        // Bind events
        const trigger = document.getElementById('cpTrigger');
        const win = document.getElementById('cpWindow');
        const close = document.getElementById('cpClose');
        const input = document.getElementById('cpInput');
        const send = document.getElementById('cpSend');

        trigger.onclick = () => win.classList.toggle('active');
        close.onclick = () => win.classList.remove('active');

        input.onkeypress = (e) => {
            if (e.key === 'Enter') handleSend();
        };
        send.onclick = handleSend;
    }

    async function handleSend() {
        const input = document.getElementById('cpInput');
        const text = input.value.trim();
        if (!text || isThinking) return;

        appendMessage('user', text);
        input.value = '';

        await botResponse(text);
    }

    function appendMessage(role, text, isTool = false) {
        const box = document.getElementById('cpMessages');
        const div = document.createElement('div');
        div.className = `cp-msg ${role}`;

        if (isTool) {
            div.innerHTML = `<div class="cp-tool-pill">⚙️ Exécution: ${text}</div>`;
        } else {
            div.innerText = text;
        }

        box.appendChild(div);
        box.scrollTop = box.scrollHeight;

        if (!isTool) {
            history.push({ role, content: text });
        }
    }

    function showTyping() {
        const box = document.getElementById('cpMessages');
        const div = document.createElement('div');
        div.className = 'cp-msg bot typing-msg';
        div.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
        box.appendChild(div);
        box.scrollTop = box.scrollHeight;
        return div;
    }

    async function botResponse(msg) {
        const typing = showTyping();
        isThinking = true;

        try {
            // For now, a mock response before we implement the backend route
            // Wait a bit to simulate thinking
            // await new Promise(r => setTimeout(r, 1000));

            const res = await fetch('/api/copilot/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: msg, history: history.slice(-10) })
            });

            typing.remove();

            if (!res.ok) {
                const err = await res.json();
                appendMessage('bot', "Désolé, j'ai rencontré une erreur : " + (err.detail || 'Erreur inconnue'));
                return;
            }

            const data = await res.json();

            // Handle tool calls if any (visualized only)
            if (data.tool_calls) {
                data.tool_calls.forEach(tc => {
                    appendMessage('bot', tc.name, true);
                });
            }

            appendMessage('bot', data.response);

        } catch (err) {
            typing.remove();
            appendMessage('bot', "Désolé, je ne peux pas répondre pour le moment. Vérifiez que le serveur est bien lancé.");
        } finally {
            isThinking = false;
        }
    }

    // Auto init
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Globally expose some functions if needed
    window.RotatorCopilot = {
        open: () => document.getElementById('cpWindow').classList.add('active'),
        close: () => document.getElementById('cpWindow').classList.remove('active'),
        say: (msg) => appendMessage('bot', msg)
    };
})();
