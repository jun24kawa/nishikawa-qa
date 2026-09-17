(() => {
  "use strict";

  const POLL_INTERVAL_MS = 4000;
  const WAITING_TIMEOUT_MS = 15 * 60 * 1000; // 15分でポーリングをあきらめる
  const ASK_POLL_INTERVAL_MS = 3000;

  const screens = {
    email: document.getElementById("screen-email"),
    waiting: document.getElementById("screen-waiting"),
    question: document.getElementById("screen-question"),
  };

  function showScreen(name) {
    Object.values(screens).forEach((el) => el.classList.remove("active"));
    screens[name].classList.add("active");
  }

  function showError(el, msg) {
    el.textContent = msg;
    el.style.display = msg ? "block" : "none";
  }

  // ---------- 画面1: メールアドレス入力 ----------
  const emailInput = document.getElementById("email-input");
  const emailErr = document.getElementById("email-err");
  const emailSubmit = document.getElementById("email-submit");

  emailSubmit.addEventListener("click", async () => {
    const email = emailInput.value.trim();
    showError(emailErr, "");
    if (!email || !email.includes("@")) {
      showError(emailErr, "メールアドレスを入力してください。");
      return;
    }
    emailSubmit.disabled = true;
    try {
      const res = await fetch("/api/request-access", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        showError(emailErr, d.error || "送信に失敗しました。時間をおいてもう一度お試しください。");
        return;
      }
      const data = await res.json();
      sessionStorage.setItem("qa_session_id", data.sessionId);
      showScreen("waiting");
      startWaitingPoll(data.sessionId);
    } catch (e) {
      showError(emailErr, "通信に失敗しました。時間をおいてもう一度お試しください。");
    } finally {
      emailSubmit.disabled = false;
    }
  });

  // ---------- 画面2: 確認待ち ----------
  const waitingStatus = document.getElementById("waiting-status");
  const waitingBack = document.getElementById("waiting-back");
  let waitingTimer = null;

  function stopWaitingPoll() {
    if (waitingTimer) { clearInterval(waitingTimer); waitingTimer = null; }
  }

  waitingBack.addEventListener("click", () => {
    stopWaitingPoll();
    sessionStorage.removeItem("qa_session_id");
    emailInput.value = "";
    showScreen("email");
  });

  function startWaitingPoll(sessionId) {
    const startedAt = Date.now();
    waitingStatus.textContent = "確認をお待ちしています…";
    stopWaitingPoll();
    waitingTimer = setInterval(async () => {
      if (Date.now() - startedAt > WAITING_TIMEOUT_MS) {
        stopWaitingPoll();
        waitingStatus.textContent =
          "確認が取れませんでした。メールが届いていないか、時間が経ちすぎています。もう一度お試しください。";
        return;
      }
      try {
        const res = await fetch(`/api/session-status?sessionId=${encodeURIComponent(sessionId)}`);
        const data = await res.json();
        if (data.status === "confirmed") {
          stopWaitingPoll();
          showScreen("question");
        } else if (data.status === "denied") {
          stopWaitingPoll();
          waitingStatus.textContent = "メールで「いいえ」が選ばれました。ご本人でない場合は、このままお待ちいただく必要はありません。";
        } else if (data.status === "expired" || data.status === "not_found") {
          stopWaitingPoll();
          waitingStatus.textContent = "確認の期限が切れました。もう一度、最初からお試しください。";
        }
        // status === "pending" のときは、そのまま待つ
      } catch (e) {
        // 通信エラーは無視して次のポーリングを待つ
      }
    }, POLL_INTERVAL_MS);
  }

  // ページを開き直したとき、確認待ち中だったら再開する
  (function resumeIfWaiting() {
    const sid = sessionStorage.getItem("qa_session_id");
    if (sid) {
      showScreen("waiting");
      startWaitingPoll(sid);
    }
  })();

  // ---------- 画面3: 質問応答 ----------
  const questionInput = document.getElementById("question-input");
  const askErr = document.getElementById("ask-err");
  const askSend = document.getElementById("ask-send");
  const askClear = document.getElementById("ask-clear");
  const askEnd = document.getElementById("ask-end");
  const answerBox = document.getElementById("answer-box");

  askClear.addEventListener("click", () => {
    questionInput.value = "";
    answerBox.innerHTML = "";
    showError(askErr, "");
  });

  askEnd.addEventListener("click", async () => {
    const sid = sessionStorage.getItem("qa_session_id");
    if (sid) {
      try {
        await fetch("/api/end-session", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ sessionId: sid }),
        });
      } catch (e) { /* 失敗しても画面は戻す */ }
    }
    sessionStorage.removeItem("qa_session_id");
    questionInput.value = "";
    answerBox.innerHTML = "";
    emailInput.value = "";
    showError(askErr, "");
    showScreen("email");
  });

  askSend.addEventListener("click", async () => {
    const sid = sessionStorage.getItem("qa_session_id");
    const question = questionInput.value.trim();
    showError(askErr, "");
    if (!sid) {
      showError(askErr, "セッションが切れています。最初からやり直してください。");
      return;
    }
    if (!question) {
      showError(askErr, "質問を入力してください。");
      return;
    }
    askSend.disabled = true;
    answerBox.innerHTML = '<p class="muted">考えています…（休止からの再開で1分ほどかかることがあります）</p>';
    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ sessionId: sid, question }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        answerBox.innerHTML = "";
        showError(askErr, d.error || "送信に失敗しました。");
        askSend.disabled = false;
        return;
      }
      const data = await res.json();
      pollAskResult(data.askId);
    } catch (e) {
      answerBox.innerHTML = "";
      showError(askErr, "通信に失敗しました。時間をおいてもう一度お試しください。");
      askSend.disabled = false;
    }
  });

  function pollAskResult(askId) {
    const timer = setInterval(async () => {
      try {
        const res = await fetch(`/api/ask-status?askId=${encodeURIComponent(askId)}`);
        const data = await res.json();
        if (data.status === "done") {
          clearInterval(timer);
          answerBox.innerHTML = "";
          const div = document.createElement("div");
          div.className = "answer";
          div.textContent = data.answer;
          answerBox.appendChild(div);
          askSend.disabled = false;
        } else if (data.status === "error") {
          clearInterval(timer);
          answerBox.innerHTML = "";
          showError(askErr, data.error || "回答の生成に失敗しました。");
          askSend.disabled = false;
        } else if (data.status === "not_found") {
          clearInterval(timer);
          answerBox.innerHTML = "";
          showError(askErr, "回答が見つかりませんでした。もう一度お試しください。");
          askSend.disabled = false;
        }
        // "processing" はそのまま待つ
      } catch (e) {
        // 通信エラーは無視して次のポーリングを待つ
      }
    }, ASK_POLL_INTERVAL_MS);
  }
})();
