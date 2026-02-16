/* NYC Scout — Full List: search, sort, load more */
(function () {
  "use strict";

  var PAGE_SIZE = 20;
  var allEvents = [];
  var filtered = [];
  var shown = 0;
  var sortMode = "score";

  // SVG icon strings
  var ICON_CAL = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/></svg>';
  var ICON_PIN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>';
  var ICON_TICKET = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z"/><path d="M13 5v2"/><path d="M13 17v2"/><path d="M13 11v2"/></svg>';

  var container = document.getElementById("event-list");
  var searchInput = document.getElementById("search-input");
  var sortScoreBtn = document.getElementById("sort-score");
  var sortDateBtn = document.getElementById("sort-date");
  var loadMoreArea = document.getElementById("load-more-area");
  var statusEl = document.getElementById("list-status");

  if (!container) return;

  // Parse embedded JSON
  var dataEl = document.getElementById("event-data");
  if (dataEl) {
    try {
      allEvents = JSON.parse(dataEl.textContent);
    } catch (e) {
      console.error("Failed to parse event data:", e);
    }
  }

  function matchesSearch(ev, query) {
    if (!query) return true;
    var q = query.toLowerCase();
    return (
      (ev.title || "").toLowerCase().indexOf(q) !== -1 ||
      (ev.artists || "").toLowerCase().indexOf(q) !== -1 ||
      (ev.venue || "").toLowerCase().indexOf(q) !== -1
    );
  }

  function sortEvents(list) {
    var sorted = list.slice();
    if (sortMode === "date") {
      sorted.sort(function (a, b) {
        return (a.start_dt || "").localeCompare(b.start_dt || "");
      });
    } else {
      sorted.sort(function (a, b) {
        return (b.score || 0) - (a.score || 0);
      });
    }
    return sorted;
  }

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function renderCard(ev) {
    var ticketHtml = "";
    if (ev.ticket_url) {
      ticketHtml =
        '<a href="' + escapeHtml(ev.ticket_url) + '" class="ticket-btn" target="_blank" rel="noopener">' +
        ICON_TICKET + " Get Tickets</a>";
    }

    var matchHtml = "";
    if (ev.match_reasons && ev.match_reasons.length) {
      matchHtml =
        '<div class="event-match"><span class="match-label">Match:</span> ' +
        escapeHtml(ev.match_reasons.join(" + ")) +
        "</div>";
    }

    var venueDisplay = escapeHtml(ev.venue);
    if (ev.neighborhood) {
      venueDisplay += ", " + escapeHtml(ev.neighborhood);
    }

    return (
      '<article class="event-card">' +
      '<div class="event-card-body">' +
      '<div class="event-card-info">' +
      '<div class="event-artist">' + escapeHtml(ev.title) + "</div>" +
      '<div class="event-meta">' +
      '<span class="event-meta-item">' + ICON_CAL + " <span>" + escapeHtml(ev.day) + " &bull; " + escapeHtml(ev.time) + "</span></span>" +
      '<span class="event-meta-item">' + ICON_PIN + ' <span class="venue-text">' + venueDisplay + "</span></span>" +
      "</div>" +
      "</div>" +
      '<div class="event-card-right">' +
      '<div class="event-score"><span class="score-number">' + Math.round(ev.score) + '</span><span class="score-label">/100</span></div>' +
      '<div class="event-price">' + escapeHtml(ev.price) + "</div>" +
      "</div>" +
      "</div>" +
      '<div class="event-card-footer">' +
      '<div class="event-footer-left">' + matchHtml + "</div>" +
      ticketHtml +
      "</div>" +
      "</article>"
    );
  }

  function render() {
    var query = searchInput ? searchInput.value : "";
    filtered = sortEvents(
      allEvents.filter(function (ev) {
        return matchesSearch(ev, query);
      })
    );

    shown = Math.min(PAGE_SIZE, filtered.length);
    container.innerHTML = filtered
      .slice(0, shown)
      .map(renderCard)
      .join("");

    updateStatus();
    updateLoadMore();
  }

  function loadMore() {
    var next = Math.min(shown + PAGE_SIZE, filtered.length);
    var html = "";
    for (var i = shown; i < next; i++) {
      html += renderCard(filtered[i]);
    }
    container.insertAdjacentHTML("beforeend", html);
    shown = next;
    updateStatus();
    updateLoadMore();
  }

  function updateStatus() {
    if (statusEl) {
      statusEl.textContent =
        "Showing " + shown + " of " + filtered.length + " matches";
    }
  }

  function updateLoadMore() {
    if (loadMoreArea) {
      loadMoreArea.style.display = shown < filtered.length ? "flex" : "none";
    }
  }

  function setSort(mode) {
    sortMode = mode;
    if (sortScoreBtn) sortScoreBtn.classList.toggle("active", mode === "score");
    if (sortDateBtn) sortDateBtn.classList.toggle("active", mode === "date");
    render();
  }

  // Event listeners
  if (searchInput) {
    searchInput.addEventListener("input", function () {
      render();
    });
  }

  if (sortScoreBtn) {
    sortScoreBtn.addEventListener("click", function () {
      setSort("score");
    });
  }

  if (sortDateBtn) {
    sortDateBtn.addEventListener("click", function () {
      setSort("date");
    });
  }

  if (loadMoreArea) {
    loadMoreArea.addEventListener("click", function () {
      loadMore();
    });
  }

  // Initial render
  render();
})();
