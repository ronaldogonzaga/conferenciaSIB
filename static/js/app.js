(() => {
  const $ = (sel) => document.querySelector(sel);

  const els = {
    loading: $("#loading"),
    dbStatus: $("#db-status"),
    refresh: $("#btn-refresh"),
    rulesList: $("#rules-list"),
    filterSeverity: $("#filter-severity"),
    filterStatus: $("#filter-status"),
    detailCategory: $("#detail-category"),
    detailTitle: $("#detail-title"),
    detailDesc: $("#detail-desc"),
    detailMeta: $("#detail-meta"),
    detailError: $("#detail-error"),
    detailOk: $("#detail-ok"),
    detailEmpty: $("#detail-empty"),
    tableHead: $("#detail-table thead"),
    tableBody: $("#detail-table tbody"),
    btnExport: $("#btn-export"),
    btnFix: $("#btn-fix"),
    fixHint: $("#fix-hint"),
    stCadusu: $("#st-cadusu"),
    stConfsib: $("#st-confsib"),
    stAtivos: $("#st-ativos"),
    stInativos: $("#st-inativos"),
    stRegrasBad: $("#st-regras-bad"),
    stFlagados: $("#st-flagados"),
    modal: $("#fix-modal"),
    modalTitle: $("#fix-modal-title"),
    modalSummary: $("#fix-modal-summary"),
    modalMeta: $("#fix-modal-meta"),
    fixTableHead: $("#fix-table thead"),
    fixTableBody: $("#fix-table tbody"),
    fixCheckAll: $("#fix-check-all"),
    btnFixClose: $("#btn-fix-close"),
    btnFixCancel: $("#btn-fix-cancel"),
    btnFixApply: $("#btn-fix-apply"),
  };

  let summary = [];
  let selectedId = null;
  let currentDetail = null;
  let previewRows = [];

  function fmt(n) {
    if (n === null || n === undefined || n === "—" || n < 0) return "—";
    return Number(n).toLocaleString("pt-BR");
  }

  function setLoading(on, msg) {
    els.loading.classList.toggle("hidden", !on);
    const text = $("#loading-text");
    if (text && msg) text.textContent = msg;
  }

  async function getJson(url, options) {
    const res = await fetch(url, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) {
      throw new Error(data.error || `Falha em ${url}`);
    }
    return data;
  }

  function updateMeta() {
    const bad = summary.filter((i) => (i.total || 0) > 0).length;
    const flagged = summary.reduce((acc, i) => acc + Math.max(i.total || 0, 0), 0);
    const pending = summary.some((i) => i.total === undefined);
    els.stRegrasBad.textContent = pending ? "…" : fmt(bad);
    els.stFlagados.textContent = pending ? "…" : fmt(flagged);
  }

  async function checkHealth() {
    try {
      const data = await getJson("/api/health");
      els.dbStatus.textContent = `DB OK · ${data.db.db} / ${data.db.schema}`;
      els.dbStatus.className = "status-pill ok";
    } catch (err) {
      els.dbStatus.textContent = `DB erro: ${err.message}`;
      els.dbStatus.className = "status-pill err";
    }
  }

  async function loadDashboard() {
    const data = await getJson("/api/dashboard");
    const t = data.totals;
    els.stCadusu.textContent = fmt(t.cadusu);
    els.stConfsib.textContent = fmt(t.confsib);
    els.stAtivos.textContent = fmt(t.ativos);
    els.stInativos.textContent = fmt(t.inativos);
  }

  function matchesFilters(item) {
    const sev = els.filterSeverity.value;
    const st = els.filterStatus.value;
    if (sev && item.severity !== sev) return false;
    if (st === "ok" && !(item.ok && item.total === 0)) return false;
    if (st === "bad" && !(item.total > 0)) return false;
    return true;
  }

  function renderRules() {
    const items = summary
      .filter(matchesFilters)
      .slice()
      .sort((a, b) => {
        const ta = a.total === undefined || a.total === null || a.total < 0 ? -1 : a.total;
        const tb = b.total === undefined || b.total === null || b.total < 0 ? -1 : b.total;
        if (tb !== ta) return tb - ta;
        return String(a.title || "").localeCompare(String(b.title || ""), "pt-BR");
      });
    els.rulesList.innerHTML = "";

    if (!items.length) {
      els.rulesList.innerHTML = `<p class="empty-state show">Nenhuma regra neste filtro.</p>`;
      return;
    }

    for (const item of items) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "rule-card";
      if (item.error) btn.classList.add("err");
      else if (item.total === undefined) btn.classList.add("pending");
      else if (item.total > 0) btn.classList.add("bad");
      else btn.classList.add("ok");
      if (item.id === selectedId) btn.classList.add("active");

      let countLabel = "…";
      if (item.error) countLabel = "!";
      else if (item.total !== undefined) countLabel = fmt(item.total);

      const fixBadge = item.fixable
        ? `<span class="badge media" title="Correção automática disponível">fix</span>`
        : "";

      btn.innerHTML = `
        <span class="title">${item.title}</span>
        <span class="count">${countLabel}</span>
        <span class="meta">
          <span class="badge ${item.severity}">${item.severity}</span>
          ${fixBadge}
          ${item.category}
        </span>
      `;
      btn.addEventListener("click", () => selectRule(item.id));
      els.rulesList.appendChild(btn);
    }
  }

  async function loadSummary() {
    setLoading(true, "Conectando e carregando regras…");
    els.detailError.classList.add("hidden");
    els.detailOk.classList.add("hidden");
    try {
      await Promise.all([checkHealth(), loadDashboard()]);
      const meta = await getJson("/api/rules");
      summary = (meta.rules || []).map((r) => ({ ...r, total: undefined, ok: false }));
      updateMeta();
      renderRules();
      setLoading(false);

      await Promise.all(
        summary.map(async (item) => {
          try {
            const res = await fetch(`/api/rule/${encodeURIComponent(item.id)}/count`);
            const data = await res.json();
            if (!res.ok || data.ok === false) {
              item.total = -1;
              item.ok = false;
              item.error = data.error || "Erro ao contar";
            } else {
              Object.assign(item, data.data);
            }
          } catch (err) {
            item.total = -1;
            item.ok = false;
            item.error = err.message;
          }
          updateMeta();
          renderRules();
        })
      );
    } catch (err) {
      els.detailError.textContent = err.message;
      els.detailError.classList.remove("hidden");
      setLoading(false);
    }
  }

  function renderTable(columns, rows) {
    els.tableHead.innerHTML = "";
    els.tableBody.innerHTML = "";

    if (!columns.length || !rows.length) {
      els.detailEmpty.classList.add("show");
      return;
    }
    els.detailEmpty.classList.remove("show");

    const trh = document.createElement("tr");
    for (const col of columns) {
      const th = document.createElement("th");
      th.textContent = col;
      trh.appendChild(th);
    }
    els.tableHead.appendChild(trh);

    for (const row of rows) {
      const tr = document.createElement("tr");
      for (const col of columns) {
        const td = document.createElement("td");
        const val = row[col];
        td.textContent = val === null || val === undefined ? "" : String(val);
        tr.appendChild(td);
      }
      els.tableBody.appendChild(tr);
    }
  }

  function updateFixUi(detail) {
    els.btnFix.classList.add("hidden");
    els.fixHint.classList.add("hidden");
    els.fixHint.classList.remove("fixable");

    if (!detail || !(detail.total > 0)) return;

    if (detail.fixable) {
      els.btnFix.classList.remove("hidden");
      els.btnFix.textContent = "Sugerir correção";
      els.fixHint.classList.remove("hidden");
      els.fixHint.classList.add("fixable");
      els.fixHint.textContent = `Correção sugerida: ${detail.fix_label}. ${detail.fix_summary}`;
    } else if (detail.manual_reason) {
      els.fixHint.classList.remove("hidden");
      els.fixHint.textContent = `Sem UPDATE automático: ${detail.manual_reason}`;
    }
  }

  async function selectRule(ruleId) {
    selectedId = ruleId;
    currentDetail = null;
    renderRules();
    setLoading(true, "Carregando inconsistências…");
    els.detailError.classList.add("hidden");
    els.detailOk.classList.add("hidden");
    els.btnExport.classList.add("hidden");
    els.btnFix.classList.add("hidden");
    els.fixHint.classList.add("hidden");

    try {
      const data = await getJson(`/api/rule/${encodeURIComponent(ruleId)}`);
      const d = data.data;
      currentDetail = d;
      els.detailCategory.textContent = d.category;
      els.detailTitle.textContent = d.title;
      els.detailDesc.textContent = d.description;
      els.detailMeta.classList.remove("hidden");
      els.detailMeta.innerHTML = `
        <span>Severidade: <strong>${d.severity}</strong></span>
        <span>Total na base: <strong>${fmt(d.total)}</strong></span>
        <span>Exibidos: <strong>${fmt(d.returned)}</strong>${d.truncated ? " (truncado)" : ""}</span>
        <span>Esperado: <strong>${d.expected_zero ? "0 registros" : "—"}</strong></span>
      `;
      renderTable(d.columns, d.rows);
      updateFixUi(d);
      if (d.total > 0) {
        els.btnExport.href = `/api/export/${encodeURIComponent(ruleId)}`;
        els.btnExport.classList.remove("hidden");
      }
    } catch (err) {
      els.detailError.textContent = err.message;
      els.detailError.classList.remove("hidden");
      renderTable([], []);
      els.detailEmpty.classList.add("show");
    } finally {
      setLoading(false);
    }
  }

  function changedFields(columns) {
    const fields = new Set();
    for (const col of columns) {
      if (col.endsWith("_atual")) fields.add(col.replace(/_atual$/, ""));
      if (col.endsWith("_novo")) fields.add(col.replace(/_novo$/, ""));
    }
    return [...fields];
  }

  function renderPreviewTable(columns, rows) {
    els.fixTableHead.innerHTML = "";
    els.fixTableBody.innerHTML = "";
    previewRows = rows;

    const fields = changedFields(columns);
    const baseCols = columns.filter(
      (c) => c !== "sel" && !c.endsWith("_atual") && !c.endsWith("_novo")
    );

    const headCols = ["sel", ...baseCols, ...fields.map((f) => `Δ ${f}`)];
    const trh = document.createElement("tr");
    for (const col of headCols) {
      const th = document.createElement("th");
      th.textContent = col === "sel" ? "" : col;
      trh.appendChild(th);
    }
    els.fixTableHead.appendChild(trh);

    for (const row of rows) {
      const tr = document.createElement("tr");
      const tdCheck = document.createElement("td");
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.className = "fix-row-check";
      cb.value = String(row.id);
      cb.checked = true;
      tdCheck.appendChild(cb);
      tr.appendChild(tdCheck);

      for (const col of baseCols) {
        const td = document.createElement("td");
        const val = row[col];
        td.textContent = val === null || val === undefined ? "" : String(val);
        tr.appendChild(td);
      }

      for (const field of fields) {
        const td = document.createElement("td");
        const oldV = row[`${field}_atual`];
        const newV = row[`${field}_novo`];
        td.innerHTML = `
          <span class="cell-change">
            <span class="cell-old">${oldV == null ? "∅" : oldV}</span>
            <span>→</span>
            <span class="cell-new">${newV == null ? "∅" : newV}</span>
          </span>
        `;
        tr.appendChild(td);
      }
      els.fixTableBody.appendChild(tr);
    }

    els.fixCheckAll.checked = true;
    syncApplyButton();
  }

  function selectedFixIds() {
    return [...els.fixTableBody.querySelectorAll(".fix-row-check:checked")].map((el) =>
      Number(el.value)
    );
  }

  function syncApplyButton() {
    const n = selectedFixIds().length;
    els.btnFixApply.disabled = n === 0;
    els.btnFixApply.textContent =
      n === 0 ? "Selecione registros" : `Gravar selecionados (${fmt(n)})`;
  }

  function closeModal() {
    els.modal.classList.add("hidden");
    previewRows = [];
  }

  async function openFixPreview() {
    if (!selectedId || !currentDetail?.fixable) return;
    setLoading(true, "Montando preview da correção…");
    els.detailError.classList.add("hidden");
    try {
      const data = await getJson(`/api/rule/${encodeURIComponent(selectedId)}/fix/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const d = data.data;
      els.modalTitle.textContent = d.label;
      els.modalSummary.textContent = d.summary;
      els.modalMeta.textContent = `${fmt(d.returned)} no preview · ${fmt(d.total_eligible)} elegíveis`;
      renderPreviewTable(d.columns, d.rows);
      els.modal.classList.remove("hidden");
      if (!d.rows.length) {
        throw new Error("Nenhum registro elegível para esta correção automática.");
      }
    } catch (err) {
      els.detailError.textContent = err.message;
      els.detailError.classList.remove("hidden");
      closeModal();
    } finally {
      setLoading(false);
    }
  }

  async function applyFix() {
    const ids = selectedFixIds();
    if (!ids.length || !selectedId) return;

    const ok = window.confirm(
      `Confirma UPDATE em ${ids.length} registro(s) da tabela cadusu?\n\nEsta ação grava no banco PostgreSQL.`
    );
    if (!ok) return;

    setLoading(true, "Gravando correções em cadusu…");
    try {
      const data = await getJson(`/api/rule/${encodeURIComponent(selectedId)}/fix/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids, confirm: true }),
      });
      closeModal();
      els.detailOk.textContent = `Correção aplicada: ${data.data.updated} de ${data.data.requested} registro(s) atualizado(s) (${data.data.label}).`;
      els.detailOk.classList.remove("hidden");
      await selectRule(selectedId);
      const item = summary.find((r) => r.id === selectedId);
      if (item) {
        try {
          const res = await getJson(`/api/rule/${encodeURIComponent(selectedId)}/count`);
          Object.assign(item, res.data);
          updateMeta();
          renderRules();
        } catch (_) {}
      }
      await loadDashboard();
    } catch (err) {
      els.detailError.textContent = err.message;
      els.detailError.classList.remove("hidden");
    } finally {
      setLoading(false);
    }
  }

  els.refresh.addEventListener("click", loadSummary);
  els.filterSeverity.addEventListener("change", renderRules);
  els.filterStatus.addEventListener("change", renderRules);
  els.btnFix.addEventListener("click", openFixPreview);
  els.btnFixClose.addEventListener("click", closeModal);
  els.btnFixCancel.addEventListener("click", closeModal);
  els.btnFixApply.addEventListener("click", applyFix);
  els.fixCheckAll.addEventListener("change", () => {
    for (const cb of els.fixTableBody.querySelectorAll(".fix-row-check")) {
      cb.checked = els.fixCheckAll.checked;
    }
    syncApplyButton();
  });
  els.fixTableBody.addEventListener("change", (ev) => {
    if (ev.target.classList.contains("fix-row-check")) syncApplyButton();
  });
  els.modal.addEventListener("click", (ev) => {
    if (ev.target === els.modal) closeModal();
  });

  loadSummary();
})();
