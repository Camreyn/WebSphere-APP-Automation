(() => {
  const fallbackHost = "10.71.1.144";
  const host = window.location.hostname && window.location.hostname !== "localhost"
    ? window.location.hostname
    : window.location.hostname || fallbackHost;
  const displayHost = host.includes(":") ? `[${host}]` : host;
  const toast = document.querySelector(".toast");
  let toastTimer;

  const endpoint = (protocol, port, path = "") => `${protocol}://${displayHost}:${port}${path}`;

  document.querySelectorAll("[data-current-host]").forEach((element) => {
    element.textContent = host;
  });

  document.querySelectorAll("[data-service-link]").forEach((link) => {
    link.href = endpoint(link.dataset.protocol, link.dataset.port, link.dataset.path || "");
    link.target = "_blank";
    link.rel = "noreferrer";
  });

  document.querySelectorAll("[data-endpoint]").forEach((element) => {
    element.textContent = endpoint(
      element.dataset.protocol,
      element.dataset.port,
      element.dataset.path || "",
    );
  });

  document.querySelectorAll("[data-plain-endpoint]").forEach((element) => {
    element.textContent = `${displayHost}:${element.dataset.port}`;
  });

  document.querySelectorAll("[data-command]").forEach((element) => {
    element.textContent = `ssh -i .secrets/ansible_lab -p ${element.dataset.port} ansible@${host}`;
  });

  document.querySelectorAll("[data-portal-url]").forEach((element) => {
    element.textContent = `${window.location.protocol}//${window.location.host}/`;
  });

  const notify = (message) => {
    clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.add("visible");
    toastTimer = setTimeout(() => toast.classList.remove("visible"), 2200);
  };

  const copyText = async (value, message) => {
    try {
      await navigator.clipboard.writeText(value);
      notify(message);
    } catch {
      const area = document.createElement("textarea");
      area.value = value;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
      notify(message);
    }
  };

  document.querySelectorAll("[data-copy-endpoint]").forEach((button) => {
    button.addEventListener("click", () => {
      const value = button.closest(".service-card").querySelector(".endpoint").textContent;
      copyText(value, "Endpoint copied");
    });
  });

  document.querySelectorAll("[data-copy-command]").forEach((button) => {
    button.addEventListener("click", () => {
      const value = button.parentElement.querySelector("code").textContent;
      copyText(value, "SSH command copied");
    });
  });

  document.querySelector("[data-copy-page]").addEventListener("click", () => {
    copyText(window.location.href, "Portal URL copied");
  });

  const filter = document.querySelector("#service-filter");
  const cards = [...document.querySelectorAll(".service-card")];
  const groups = [...document.querySelectorAll(".service-group")].filter((group) => group.querySelector(".service-card"));
  const emptyState = document.querySelector(".empty-state");

  filter.addEventListener("input", () => {
    const query = filter.value.trim().toLowerCase();
    let visibleCards = 0;
    cards.forEach((card) => {
      const visible = !query || `${card.dataset.search} ${card.textContent}`.toLowerCase().includes(query);
      card.hidden = !visible;
      if (visible) visibleCards += 1;
    });
    groups.forEach((group) => {
      group.hidden = !group.querySelector(".service-card:not([hidden])");
    });
    emptyState.hidden = visibleCards !== 0;
  });

  window.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      filter.focus();
    }
    if (event.key === "Escape" && document.activeElement === filter) {
      filter.value = "";
      filter.dispatchEvent(new Event("input"));
      filter.blur();
    }
  });
})();
