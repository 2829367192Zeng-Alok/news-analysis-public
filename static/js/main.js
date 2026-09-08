async function fetchJSON(url) {
  const resp = await fetch(url);
  if (!resp.ok) {
    throw new Error("请求失败: " + resp.status);
  }
  return await resp.json();
}

function formatDirectionImpact(direction, impact) {
  let dirText = "中性";
  if (direction > 0) dirText = "利好";
  if (direction < 0) dirText = "利空";
  const impText = impact ? ` | 强度 ${impact}` : "";
  return dirText + impText;
}

function directionClass(direction) {
  if (direction > 0) return "badge badge-positive";
  if (direction < 0) return "badge badge-negative";
  return "badge badge-neutral";
}

// 模型输出字段（来自外部新闻 → LLM → 数据库）不可信，进 innerHTML 前必须转义。
function escapeHtml(s) {
  if (s == null) return "";
  const div = document.createElement("div");
  div.textContent = String(s);
  return div.innerHTML;
}

let currentNewsId = null;

async function loadStats() {
  try {
    const data = await fetchJSON("/api/stats");
    const statsEl = document.getElementById("stats");
    statsEl.textContent =
      `已分析新闻：${data.total_news} 条` +
      (data.latest_news_time ? ` | 最新：${data.latest_news_time.replace("T", " ").slice(0, 19)}` : "");
  } catch (e) {
    console.error(e);
  }
}

async function loadNewsList() {
  try {
    const data = await fetchJSON("/api/news");
    const container = document.getElementById("news-list-container");
    container.innerHTML = "";
    if (!data.items || data.items.length === 0) {
      container.textContent = "暂无数据，请等待定时任务拉取并分析新闻。";
      return;
    }
    data.items.forEach((item) => {
      const div = document.createElement("div");
      div.className = "news-item";
      div.dataset.id = item.id;

      const title = document.createElement("div");
      title.className = "news-title";
      title.textContent = item.title;

      const meta = document.createElement("div");
      meta.className = "news-meta";
      const left = document.createElement("span");
      left.textContent = `${item.source || ""} | ${item.news_datetime ? item.news_datetime.replace("T", " ").slice(0, 19) : ""}`;

      const right = document.createElement("span");
      const badge = document.createElement("span");
      badge.className = directionClass(item.direction || 0);
      badge.textContent = formatDirectionImpact(item.direction || 0, item.impact || 0);
      right.appendChild(badge);

      meta.appendChild(left);
      meta.appendChild(right);

      div.appendChild(title);
      div.appendChild(meta);

      div.addEventListener("click", () => {
        document
          .querySelectorAll(".news-item")
          .forEach((el) => el.classList.remove("active"));
        div.classList.add("active");
        currentNewsId = item.id;
        loadDetail(item.id);
      });

      container.appendChild(div);
    });

    if (currentNewsId === null && data.items.length > 0) {
      currentNewsId = data.items[0].id;
      document
        .querySelector(`.news-item[data-id="${currentNewsId}"]`)
        ?.classList.add("active");
      loadDetail(currentNewsId);
    }
  } catch (e) {
    console.error(e);
  }
}

async function loadDetail(id) {
  try {
    const data = await fetchJSON(`/api/news/${id}`);
    const container = document.getElementById("detail-container");
    container.innerHTML = "";

    const blocks = [];

    blocks.push({
      title: "核心结论",
      content: data.conclusion ? escapeHtml(data.conclusion) : "无",
    });

    blocks.push({
      title: "投资启示",
      content: data.insight ? escapeHtml(data.insight) : "无",
    });

    blocks.push({
      title: "时间维度结论",
      content: [
        data.shorttime ? `短期：${escapeHtml(data.shorttime)}` : null,
        data.midtime ? `中期：${escapeHtml(data.midtime)}` : null,
        data.longtime ? `长期：${escapeHtml(data.longtime)}` : null,
      ]
        .filter(Boolean)
        .join("<br>") || "无",
    });

    blocks.push({
      title: "各维度分析",
      content:
        [
          data.interest ? `实际利率：${escapeHtml(data.interest)}` : null,
          data.dollar ? `美元指数：${escapeHtml(data.dollar)}` : null,
          data.warrisk ? `地缘政治风险：${escapeHtml(data.warrisk)}` : null,
          data.liquidity ? `资本市场流动性：${escapeHtml(data.liquidity)}` : null,
          data.emotion ? `市场情绪：${escapeHtml(data.emotion)}` : null,
        ]
          .filter(Boolean)
          .join("<br>") || "无",
    });

    blocks.forEach((b) => {
      const blockEl = document.createElement("div");
      blockEl.className = "detail-block";
      const h3 = document.createElement("h3");
      h3.textContent = b.title;
      const p = document.createElement("p");
      p.innerHTML = b.content;
      blockEl.appendChild(h3);
      blockEl.appendChild(p);
      container.appendChild(blockEl);
    });

    if (Array.isArray(data.keyword) && data.keyword.length > 0) {
      const blockEl = document.createElement("div");
      blockEl.className = "detail-block";
      const h3 = document.createElement("h3");
      h3.textContent = "关键词";
      const row = document.createElement("div");
      row.className = "pill-row";
      data.keyword.forEach((kw) => {
        const pill = document.createElement("span");
        pill.className = "pill";
        pill.textContent = kw;
        row.appendChild(pill);
      });
      blockEl.appendChild(h3);
      blockEl.appendChild(row);
      container.appendChild(blockEl);
    }
  } catch (e) {
    console.error(e);
  }
}

// ── 近实时更新 ─────────────────────────────────────────────────────
// 首选 SSE（/api/stream，服务端 5s 检测变化，有新数据立即推送）；
// SSE 不可用时回退为 5s 定时轮询。

let refreshFailures = 0;
const FALLBACK_POLL_MS = 5000;

function nextRefreshDelay() {
  const delay = Math.min(FALLBACK_POLL_MS * Math.pow(2, refreshFailures), 60000);
  return delay;
}

async function refreshTick() {
  try {
    await Promise.all([loadStats(), loadNewsList()]);
    refreshFailures = 0;
  } catch (e) {
    refreshFailures = Math.min(refreshFailures + 1, 5);
  }
}

function startSse() {
  try {
    const es = new EventSource("/api/stream");
    es.onmessage = (ev) => {
      try {
        const payload = JSON.parse(ev.data);
        if (payload && payload.type === "update") {
          loadStats();
          loadNewsList();
        }
      } catch (_) { /* 忽略解析失败，等待下一条 */ }
    };
    es.onerror = () => {
      // 连接断开：EventSource 会自动重连；若浏览器报错则关闭并退化轮询
      es.close();
      startFallbackPolling();
    };
    return true;
  } catch (_) {
    return false;
  }
}

function startFallbackPolling() {
  loadStats();
  loadNewsList();
  setTimeout(async function tick() {
    await refreshTick();
    setTimeout(tick, nextRefreshDelay());
  }, nextRefreshDelay());
}

function setupAutoRefresh() {
  loadStats();
  loadNewsList();
  if (typeof EventSource === "undefined" || !startSse()) {
    startFallbackPolling();
  }
}

window.addEventListener("DOMContentLoaded", setupAutoRefresh);

