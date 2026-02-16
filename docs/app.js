/* NYC Scout — Full List: search, sort, load more */
(function () {
  "use strict";

  var PAGE_SIZE = 20;
  var allEvents = [];
  var filtered = [];
  var shown = 0;
  var sortMode = "score"; // "score" or "date"

  var container = document.getElementById("event-list");
  var searchInput = document.getElementById("search-input");
  var sortSelect = document.getElementById("sort-select");
  var loadMoreBtn = document.getElementById("load-more-btn");
  var statusEl = document.getElementById("list-status");

  if (!container) return; // Not on the list page

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

  function scoreClass(score) {
    if (score >= 65) return "high";
    if (score >= 40) return "mid";
    return "low";
  }

  function renderCard(ev) {
    var ticketHtml = "";
    if (ev.ticket_url) {
      ticketHtml =
        '<div class="event-actions"><a href="' +
        ev.ticket_url +
        '" class="ticket-btn" target="_blank" rel="noopener">\ud83c\udfab Get Tickets</a></div>';
    }

    var matchHtml = "";
    if (ev.match_reasons && ev.match_reasons.length) {
      matchHtml =
        '<div class="event-match"><span class="match-label">Match: </span>' +
        '<span class="match-text">' +
        ev.match_reasons.join(" + ") +
        "</span></div>";
    }

    return (
      '<article class="event-card">' +
      '<div class="event-info">' +
      '<div class="event-title"><a href="' + (ev.ticket_url || "#") + '">' +
      ev.title +
      "</a></div>" +
      '<div class="event-meta">\ud83d\udcc5 ' +
      ev.day +
      " \u2022 " +
      ev.time +
      '  \ud83d\udccd ' +
      ev.venue +
      (ev.neighborhood ? ", " + ev.neighborhood : "") +
      "    [" +
      ev.price +
      "]</div>" +
      matchHtml +
      "</div>" +
      '<div class="event-score"><div class="score-number ' +
      scoreClass(ev.score) +
      '">' +
      Math.round(ev.score) +
      '</div><div class="score-label">/100</div></div>' +
      ticketHtml +
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
        "Showing " + shown + " of " + filtered.length + " events";
    }
  }

  function updateLoadMore() {
    if (loadMoreBtn) {
      loadMoreBtn.style.display = shown < filtered.length ? "block" : "none";
    }
  }

  // Event listeners
  if (searchInput) {
    searchInput.addEventListener("input", function () {
      render();
    });
  }

  if (sortSelect) {
    sortSelect.addEventListener("change", function () {
      sortMode = sortSelect.value;
      render();
    });
  }

  if (loadMoreBtn) {
    loadMoreBtn.addEventListener("click", function () {
      loadMore();
    });
  }

  // Initial render
  render();
})();
