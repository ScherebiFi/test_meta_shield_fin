const apiBase = window.location.protocol === "file:"
    ? "http://127.0.0.1:8000"
    : window.location.origin;
const wsUrl = `${apiBase.replace(/^http/, "ws")}/ws`;

let totalTransactions = 0;
let reconnectDelay = 1000;
const txTableBody = document.getElementById("txTableBody");
const inspectionPanel = document.getElementById("inspectionPanel");
const failSafeBtn = document.getElementById("failSafeBtn");
const failSafeStatus = document.getElementById("failSafeStatus");
const connectionStatus = document.getElementById("connectionStatus");

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
    })[character]);
}

function connectWebSocket() {
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        reconnectDelay = 1000;
        connectionStatus.textContent = "WebSocket connecté";
        connectionStatus.className = "text-xs px-3 py-1 bg-emerald-900/50 text-emerald-300 rounded-full border border-emerald-700";
    };

    ws.onclose = () => {
        connectionStatus.textContent = "Déconnecté — reconnexion…";
        connectionStatus.className = "text-xs px-3 py-1 bg-rose-900/50 text-rose-300 rounded-full border border-rose-700";
        window.setTimeout(connectWebSocket, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, 15000);
    };

    ws.onerror = () => ws.close();
    ws.onmessage = (event) => {
        let data;
        try {
            data = JSON.parse(event.data);
        } catch (error) {
            console.error("Message WebSocket invalide :", error);
            return;
        }

        if (data.type === "SYSTEM_STATE") {
            updateFailSafeUI(data.fail_safe_active, data.reason);
            return;
        }

        if (data.type === "TRANSACTION_PROCESSED") {
            totalTransactions++;
            document.getElementById("txCount").textContent = `${totalTransactions} analysées`;
            addTransactionRow(data);
        }
    };
}

connectWebSocket();

function addTransactionRow(data) {
    const tx = data.transaction;
    const analysis = data.analysis;
    const row = document.createElement("tr");
    row.className = "hover:bg-gray-800/50 transition cursor-pointer";

    let badgeColor = "bg-emerald-900/40 text-emerald-400 border-emerald-700";
    if (analysis.action === "BLOCK" || analysis.status.includes("BLOCKED")) {
        badgeColor = "bg-rose-900/40 text-rose-400 border-rose-700";
    } else if (analysis.status === "GREY_ZONE" || analysis.action === "CHALLENGE_2FA") {
        badgeColor = "bg-amber-900/40 text-amber-400 border-amber-700";
    }

    const transactionId = escapeHtml(tx.transaction_id);
    const amount = escapeHtml(tx.amount);
    const velocity = escapeHtml(tx.velocity);
    const action = escapeHtml(analysis.action);
    const hash = escapeHtml(analysis.integrity_hash);
    row.innerHTML = `
        <td class="py-3 px-3 font-mono text-xs text-indigo-300">${transactionId}</td>
        <td class="py-3 px-3 font-semibold text-white">${amount} €</td>
        <td class="py-3 px-3 text-gray-300">${velocity} req/m</td>
        <td class="py-3 px-3">
            <span class="text-xs px-2.5 py-1 rounded-full border ${badgeColor}">${action}</span>
        </td>
        <td class="py-3 px-3 font-mono text-xs text-gray-500 truncate max-w-[120px]">${hash.substring(0, 10)}...</td>
    `;
    row.querySelector("td:last-child").title = analysis.integrity_hash;
    row.onclick = () => showInspection(data);
    txTableBody.prepend(row);

    if (txTableBody.children.length > 50) {
        txTableBody.removeChild(txTableBody.lastChild);
    }
}

function showInspection(data) {
    const tx = data.transaction;
    const analysis = data.analysis;
    const reportHtml = data.ai_report
        ? `
            <div class="mt-2 text-left bg-gray-950 p-3 rounded border border-indigo-900/50 text-xs text-indigo-200">
                <p class="font-bold text-indigo-400 mb-1">Rapport de conformité AML/KYC :</p>
                <p>${escapeHtml(data.ai_report)}</p>
            </div>
        `
        : `<p class="text-gray-400 italic">Aucun rapport LLM requis (traitement local).</p>`;

    inspectionPanel.innerHTML = `
        <div class="w-full text-left space-y-3">
            <div class="flex justify-between items-center border-b border-bordercol pb-2">
                <span class="font-mono text-white font-bold">${escapeHtml(tx.transaction_id)}</span>
                <span class="text-xs text-gray-400">${escapeHtml(tx.timestamp)}</span>
            </div>
            <div class="grid grid-cols-2 gap-2 text-xs">
                <div class="bg-gray-900 p-2 rounded">Montant : <b class="text-white">${escapeHtml(tx.amount)} €</b></div>
                <div class="bg-gray-900 p-2 rounded">Vélocité : <b class="text-white">${escapeHtml(tx.velocity)} req/m</b></div>
            </div>
            <div class="bg-gray-900 p-2 rounded text-xs">
                Décision : <b class="text-white">${escapeHtml(analysis.action)}</b><br>
                Motif ML : <span class="text-gray-300">${escapeHtml(analysis.reason)}</span>
                ${analysis.latency_ms == null ? "" : `<br>Latence ML : ${escapeHtml(analysis.latency_ms)} ms`}
            </div>
            <div class="bg-gray-900 p-2 rounded text-xs font-mono break-all">
                Hash SHA-256 : <span class="text-indigo-400">${escapeHtml(analysis.integrity_hash)}</span>
            </div>
            ${reportHtml}
        </div>
    `;
}

async function toggleFailSafe() {
    failSafeBtn.disabled = true;
    try {
        const response = await fetch(`${apiBase}/api/toggle-failsafe`, { method: "POST" });
        if (!response.ok) {
            throw new Error(`Le serveur a répondu ${response.status}`);
        }
        const data = await response.json();
        updateFailSafeUI(data.fail_safe_active, data.reason);
    } catch (error) {
        console.error("Erreur lors du basculement Fail-Safe :", error);
        failSafeStatus.textContent = "ERREUR DE CONNEXION";
        failSafeStatus.title = "Impossible de modifier l'état du mode de secours.";
    } finally {
        failSafeBtn.disabled = false;
    }
}

function updateFailSafeUI(isActive, reason = "") {
    failSafeStatus.title = reason;
    if (isActive) {
        failSafeStatus.textContent = "ACTIF (Secours Local)";
        failSafeStatus.className = "text-rose-400 font-bold";
        failSafeBtn.className = "px-4 py-2 rounded-lg text-sm font-semibold transition border border-rose-600 bg-rose-950 hover:bg-rose-900 text-rose-200";
    } else {
        failSafeStatus.textContent = "INACTIF (Cloud)";
        failSafeStatus.className = "text-emerald-400";
        failSafeBtn.className = "px-4 py-2 rounded-lg text-sm font-semibold transition border border-gray-600 bg-gray-800 hover:bg-gray-700 text-gray-300";
    }
}
