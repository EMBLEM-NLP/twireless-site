/* T Wireless: live open/closed signs, today's hours, deal filters, map loader.
   No dependencies. Everything here is an enhancement; pages work without it. */
(function () {
  "use strict";

  var DAY_INDEX = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
  var DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

  function nowIn(tz) {
    try {
      var parts = new Intl.DateTimeFormat("en-US", {
        timeZone: tz, weekday: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23"
      }).formatToParts(new Date());
      var map = {};
      parts.forEach(function (p) { map[p.type] = p.value; });
      return { day: DAY_INDEX[map.weekday], minutes: (parseInt(map.hour, 10) % 24) * 60 + parseInt(map.minute, 10) };
    } catch (err) {
      var d = new Date();
      return { day: d.getDay(), minutes: d.getHours() * 60 + d.getMinutes() };
    }
  }

  function toMinutes(hhmm) {
    var p = hhmm.split(":");
    return parseInt(p[0], 10) * 60 + parseInt(p[1], 10);
  }

  function timeLabel(hhmm) {
    var m = toMinutes(hhmm), h = Math.floor(m / 60), min = m % 60;
    var h12 = h % 12 || 12;
    return (min ? h12 + ":" + (min < 10 ? "0" : "") + min : String(h12)) + (h < 12 ? " a.m." : " p.m.");
  }

  function storeStatus(hours, now) {
    var today = hours[now.day];
    if (today) {
      var open = toMinutes(today[0]), close = toMinutes(today[1]);
      if (now.minutes >= open && now.minutes < close) {
        return { open: true, text: "until " + timeLabel(today[1]) + " today" };
      }
      if (now.minutes < open) {
        return { open: false, text: "Opens today at " + timeLabel(today[0]) };
      }
    }
    for (var i = 1; i <= 7; i++) {
      var d = (now.day + i) % 7;
      if (hours[d]) {
        return { open: false, text: "Opens " + (i === 1 ? "tomorrow" : DAY_NAMES[d]) + " at " + timeLabel(hours[d][0]) };
      }
    }
    return { open: false, text: "Call us for today's hours" };
  }

  var tz = "America/Toronto";

  // Open / closed sign
  var current = null;
  document.querySelectorAll(".status[data-hours]").forEach(function (node) {
    var hours;
    try { hours = JSON.parse(node.getAttribute("data-hours")); } catch (err) { return; }
    tz = node.getAttribute("data-tz") || tz;
    var s = storeStatus(hours, nowIn(tz));
    var sign = node.querySelector(".status__sign");
    var text = node.querySelector(".status__text");
    if (!sign || !text) { return; }
    sign.textContent = s.open ? "Open" : "Closed";
    text.textContent = s.text;
    sign.classList.remove("is-pending");
    node.classList.add(s.open ? "is-open" : "is-closed");
    current = s;
  });

  // The neon sign in the storefront illustration follows the same status
  document.querySelectorAll(".storefront").forEach(function (art) {
    if (!current) { return; }
    var neon = art.querySelector(".storefront__neon-text");
    if (neon && !current.open) { neon.textContent = "Closed"; }
    art.classList.remove("is-pending");
    art.classList.add(current.open ? "is-open" : "is-closed");
  });

  // Today's row in the hours tables
  var today = nowIn(tz).day;
  document.querySelectorAll(".hours tr[data-day]").forEach(function (row) {
    if (Number(row.getAttribute("data-day")) === today) { row.classList.add("is-today"); }
  });

  // Deal filters
  var filters = document.querySelector(".filters");
  var grid = document.querySelector("[data-offers]");
  if (filters && grid) {
    var empty = document.querySelector("[data-offers-empty]");
    filters.classList.remove("filters--pending");
    filters.addEventListener("click", function (event) {
      var button = event.target.closest("[data-filter]");
      if (!button) { return; }
      var group = button.getAttribute("data-filter");
      var shown = 0;
      filters.querySelectorAll("[data-filter]").forEach(function (b) {
        b.setAttribute("aria-pressed", String(b === button));
      });
      grid.querySelectorAll(".offer").forEach(function (card) {
        var match = group === "all" || card.getAttribute("data-category") === group;
        card.hidden = !match;
        if (match) { shown++; }
      });
      if (empty) { empty.hidden = shown > 0; }
    });
  }

  // Map: load Google Maps only when someone asks for it
  document.querySelectorAll(".map[data-map-query]").forEach(function (map) {
    var button = map.querySelector("[data-map-load]");
    if (!button) { return; }
    button.classList.remove("is-pending");
    button.addEventListener("click", function () {
      var query = map.getAttribute("data-map-query");
      var frame = document.createElement("iframe");
      frame.src = "https://www.google.com/maps?q=" + encodeURIComponent(query) + "&output=embed";
      frame.title = "Map of " + query;
      frame.referrerPolicy = "strict-origin-when-cross-origin";
      frame.allowFullscreen = true;
      map.appendChild(frame);
      var facade = map.querySelector(".map__facade");
      if (facade) { facade.remove(); }
      frame.focus();
    });
  });
})();
