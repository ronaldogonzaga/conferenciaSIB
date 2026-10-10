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
    sourceLegend: $("#source-legend"),
    tableHead: $("#detail-table thead"),
    tableBody: $("#detail-table tbody"),
    btnExport: $("#btn-export"),
    btnFix: $("#btn-fix"),
    fixHint: $("#fix-hint"),
    stCadusu: $("#st-cadusu"),
    stConfsib: $("#st-confsib"),
    stPending: $("#st-pending"),
    stAtivos: $("#st-ativos"),
    stInativos: $("#st-inativos"),
    stRegrasBad: $("#st-regras-bad"),
    stFlagados: $("#st-flagados"),
    modal: $("#fix-modal"),
    modalTitle: $("#fix-modal-title"),
    modalSummary: $("#fix-modal-summary"),
    modalMeta: $("#fix-modal-meta"),
    fixSourceLegend: $("#fix-source-legend"),
    fixTableHead: $("#fix-table thead"),
    fixTableBody: $("#fix-table tbody"),
    fixCheckAll: $("#fix-check-all"),
    btnFixClose: $("#btn-fix-close"),
    btnFixCancel: $("#btn-fix-cancel"),
    btnFixApply: $("#btn-fix-apply"),
    rpxForm: $("#rpx-form"),
    rpxPath: $("#rpx-path"),
    rpxFile: $("#rpx-file"),
    rpxError: $("#rpx-error"),
    rpxOk: $("#rpx-ok"),
    rpxSummary: $("#rpx-summary"),
    rpxErrorsList: $("#rpx-errors-list"),
    rpxTableWrap: $("#rpx-table-wrap"),
    rpxFilterCode: $("#rpx-filter-code"),
    rpxFilterMov: $("#rpx-filter-mov"),
    rpxTableMeta: $("#rpx-table-meta"),
    rpxTableHead: $("#rpx-table thead"),
    rpxTableBody: $("#rpx-table tbody"),
  };

  let summary = [];
  let selectedId = null;
  let currentDetail = null;
  let previewRows = [];
  let rpxData = null;

  function fmt(n) {
    if (n === null || n === undefined || n === "—" || n < 0) return "—";
    return Number(n).toLocaleString("pt-BR");
  }

  function escapeAttr(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;");
  }

  function parseDateValue(val) {
    if (val === null || val === undefined || val === "") return null;
    const s = String(val).trim();
    // ISO (YYYY-MM-DD) ou com hora
    let d = new Date(s);
    if (!Number.isNaN(d.getTime())) return d;
    // DD/MM/YYYY
    const m = s.match(/^(\d{2})\/(\d{2})\/(\d{4})/);
    if (m) {
      d = new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1]));
      if (!Number.isNaN(d.getTime())) return d;
    }
    return null;
  }

  function datainiColumn(columns) {
    return columns.find((c) => String(c).toLowerCase() === "dataini") || null;
  }

  function sortRowsByDatainiDesc(rows, col) {
    return [...rows].sort((a, b) => {
      const da = parseDateValue(a[col]);
      const db = parseDateValue(b[col]);
      const ta = da ? da.getTime() : Number.NEGATIVE_INFINITY;
      const tb = db ? db.getTime() : Number.NEGATIVE_INFINITY;
      return tb - ta;
    });
  }

  const META_COLS = new Set([
    "chave_usada",
    "situacao_correcao",
    "comparacao_ans",
    "sel",
  ]);

  function columnSource(colName, ctx) {
    const c = String(colName || "").toLowerCase();
    if (!c || META_COLS.has(c) || c.startsWith("Δ ")) return "meta";
    if (
      c.endsWith("_ans") ||
      c.endsWith("_confsib") ||
      c.endsWith("_ans_raw") ||
      c.endsWith("_contratante_ans")
    ) {
      return "confsib";
    }
    if (c === "nome_local") return "cadusu";
    if (ctx && ctx.confsibOnly) return "confsib";
    if (c.endsWith("_atual") || c.endsWith("_novo")) return "cadusu";
    return "cadusu";
  }

  function detectColumnContext(columns) {
    const cols = columns.map((c) => String(c).toLowerCase());
    const hasAns = cols.some(
      (c) =>
        c.endsWith("_ans") ||
        c.endsWith("_confsib") ||
        c.endsWith("_ans_raw") ||
        c === "nome_ans"
    );
    const confsibOnly =
      cols.includes("numseq") &&
      (cols.includes("flag") || cols.includes("registro")) &&
      !cols.includes("id") &&
      !hasAns;
    return { hasAns, confsibOnly, mixed: hasAns || confsibOnly };
  }

  function applySourceClass(el, source) {
    el.classList.remove("col-cadusu", "col-confsib", "col-meta");
    if (source === "cadusu") el.classList.add("col-cadusu");
    else if (source === "confsib") el.classList.add("col-confsib");
    else el.classList.add("col-meta");
    if (source === "cadusu") el.title = "cadusu (base local)";
    else if (source === "confsib") el.title = "confsib (retorno ANS)";
  }

  function syncSourceLegend(legendEl, columns) {
    if (!legendEl) return;
    const ctx = detectColumnContext(columns);
    const sources = new Set(
      columns.map((c) => columnSource(c, ctx)).filter((s) => s !== "meta")
    );
    const show = sources.has("cadusu") && sources.has("confsib");
    legendEl.classList.toggle("hidden", !show);
    legendEl.setAttribute("aria-hidden", show ? "false" : "true");
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
    const pending = t.pending_confsib?.total_aguardando;
    if (els.stPending) {
      els.stPending.textContent = fmt(pending);
      els.stPending.title = pending
        ? `Correções aguardando retorno confsib (~${t.pending_confsib?.wait_days || 45} dias)`
        : "Nenhuma correção aguardando retorno confsib";
    }
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

      const tip = item.fix_tip || item.fix_summary || "";
      const fixBadge = item.fixable
        ? `<span class="badge media" title="${escapeAttr(
            tip || "Correção automática disponível"
          )}">fix</span>`
        : "";
      const extraBadges = (item.ui_badges || [])
        .map(
          (b) =>
            `<span class="badge ${escapeAttr(b.class || "info")}" title="${escapeAttr(
              b.title || b.label || ""
            )}">${escapeAttr(b.label || "")}</span>`
        )
        .join("");

      btn.innerHTML = `
        <span class="title">${item.title}</span>
        <span class="count">${countLabel}</span>
        <span class="meta">
          <span class="badge ${item.severity}">${item.severity}</span>
          ${fixBadge}
          ${extraBadges}
          ${item.category}
        </span>
      `;
      if (tip) btn.title = tip;
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

  function renderTable(columns, rows, opts = {}) {
    els.tableHead.innerHTML = "";
    els.tableBody.innerHTML = "";

    if (!columns.length || !rows.length) {
      els.detailEmpty.classList.add("show");
      if (els.sourceLegend) {
        els.sourceLegend.classList.add("hidden");
        els.sourceLegend.setAttribute("aria-hidden", "true");
      }
      return;
    }
    els.detailEmpty.classList.remove("show");

    const isCritica = opts.severity === "critica";
    const diCol = datainiColumn(columns);
    const statusCol = columns.find(
      (c) => String(c).toLowerCase() === "situacao_correcao"
    );
    let displayRows = rows;
    if (statusCol) {
      displayRows = [...rows].sort((a, b) => {
        const ca = String(a[statusCol] || "")
          .toLowerCase()
          .startsWith("corrigido")
          ? 1
          : 0;
        const cb = String(b[statusCol] || "")
          .toLowerCase()
          .startsWith("corrigido")
          ? 1
          : 0;
        if (ca !== cb) return ca - cb;
        if (!diCol) return 0;
        const da = parseDateValue(a[diCol]);
        const db = parseDateValue(b[diCol]);
        const ta = da ? da.getTime() : Number.NEGATIVE_INFINITY;
        const tb = db ? db.getTime() : Number.NEGATIVE_INFINITY;
        return tb - ta;
      });
    } else if (isCritica && diCol) {
      displayRows = sortRowsByDatainiDesc(rows, diCol);
    }

    const trh = document.createElement("tr");
    const colCtx = detectColumnContext(columns);
    syncSourceLegend(els.sourceLegend, columns);
    for (const col of columns) {
      const th = document.createElement("th");
      th.textContent = col;
      applySourceClass(th, columnSource(col, colCtx));
      trh.appendChild(th);
    }
    els.tableHead.appendChild(trh);

    for (const row of displayRows) {
      const tr = document.createElement("tr");
      const statusVal = statusCol ? String(row[statusCol] || "") : "";
      const corrigido = statusVal.toLowerCase().startsWith("corrigido");

      if (corrigido) {
        tr.classList.add("row-correcao-aplicada");
        tr.title = statusVal || "Correção já aplicada — aguardando ANS";
      }

      for (const col of columns) {
        const td = document.createElement("td");
        const val = row[col];
        td.textContent = val === null || val === undefined ? "" : String(val);
        applySourceClass(td, columnSource(col, colCtx));

        if (corrigido && statusCol && col === statusCol) {
          td.classList.add("cell-correcao-aplicada");
          const mark = document.createElement("span");
          mark.className = "correcao-aplicada-flag";
          mark.textContent = " ✓";
          td.appendChild(mark);
        }
        tr.appendChild(td);
      }
      els.tableBody.appendChild(tr);
    }
  }

  function updateFixUi(detail) {
    els.btnFix.classList.add("hidden");
    els.fixHint.classList.add("hidden");
    els.fixHint.classList.remove("fixable");
    els.btnFix.removeAttribute("title");
    els.fixHint.removeAttribute("title");

    if (!detail || !(detail.total > 0)) return;

    const tip = detail.fix_tip || detail.fix_summary || detail.manual_reason || "";

    if (detail.fixable) {
      els.btnFix.classList.remove("hidden");
      els.btnFix.textContent = "Sugerir correção";
      els.fixHint.classList.remove("hidden");
      els.fixHint.classList.add("fixable");
      els.fixHint.textContent = `Correção sugerida: ${detail.fix_label}. ${detail.fix_summary}`;
      if (tip) {
        els.btnFix.title = tip;
        els.fixHint.title = tip;
      }
    } else if (detail.manual_reason) {
      els.fixHint.classList.remove("hidden");
      els.fixHint.textContent = `Sem UPDATE automático: ${detail.manual_reason}`;
      if (tip) els.fixHint.title = tip;
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
        ${
          (d.ui_badges || [])
            .map(
              (b) =>
                `<span class="badge ${escapeAttr(b.class || "info")}" title="${escapeAttr(
                  b.title || b.label || ""
                )}">${escapeAttr(b.label || "")}</span>`
            )
            .join("")
        }
        ${
          d.severity === "critica"
            ? `<span class="meta-dataini-hint">Ordenado por <strong>dataini</strong> ↓</span>`
            : ""
        }
        ${
          d.id === "ativo_inativo_confsib_reinclusao"
            ? `<span class="meta-correcao-hint">Verde = correção já aplicada (aguardando ANS)</span>`
            : ""
        }
      `;
      renderTable(d.columns, d.rows, { severity: d.severity });
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
      const tip = currentDetail?.fix_tip || d.summary || "";
      els.modalTitle.title = tip;
      els.modalSummary.title = tip;
      els.modalMeta.textContent = `${fmt(d.returned)} no preview · ${fmt(d.total_eligible)} elegíveis`;
      els.modalMeta.title = tip;
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
      const pendingN = data.data.pending_confsib_registered || 0;
      els.detailOk.textContent =
        `Correção aplicada: ${data.data.updated} de ${data.data.requested} registro(s) atualizado(s) (${data.data.label}).` +
        (pendingN
          ? ` ${pendingN} enviado(s) para aguardando retorno confsib (não listar de novo ~45 dias).`
          : "");
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

  function renderRpxSummary(data) {
    const h = data.header || {};
    const p = data.protocolo || {};
    const r = data.resumo || {};
    const tot = (data.consolidado && data.consolidado.total) || {};
    els.rpxSummary.classList.remove("hidden");
    els.rpxSummary.innerHTML = `
      <div class="rpx-chip"><span class="label">Protocolo</span><span class="value">${escapeAttr(
        p.numero_protocolo || "—"
      )}</span></div>
      <div class="rpx-chip"><span class="label">Arquivo origem</span><span class="value" style="font-size:0.95rem">${escapeAttr(
        p.nome_arquivo || data.source_name || "—"
      )}</span></div>
      <div class="rpx-chip"><span class="label">Registro ANS</span><span class="value">${escapeAttr(
        h.registro_ans || "—"
      )}</span></div>
      <div class="rpx-chip"><span class="label">Rejeitados</span><span class="value">${fmt(
        r.total_rejeitados
      )}</span></div>
      <div class="rpx-chip"><span class="label">Incluídos OK</span><span class="value">${fmt(
        r.total_incluidos
      )}</span></div>
      <div class="rpx-chip"><span class="label">Match cadusu</span><span class="value">${fmt(
        data.matched_cadusu
      )}</span></div>
      <div class="rpx-chip"><span class="label">Processados (total)</span><span class="value">${fmt(
        tot.quantidade_processados
      )}</span></div>
      <div class="rpx-chip"><span class="label">% acerto</span><span class="value">${
        tot.percentual_acerto != null
          ? Number(tot.percentual_acerto).toLocaleString("pt-BR", {
              maximumFractionDigits: 2,
            }) + "%"
          : "—"
      }</span></div>
    `;
  }

  function rejeitadosForError(codigo) {
    const code = String(codigo || "");
    return (rpxData?.rejeitados || []).filter((r) => {
      if (r.codigo_erro === code) return true;
      return (r.erros || []).some((e) => e.codigo_erro === code);
    });
  }

  function ccosForError(codigo) {
    return [
      ...new Set(
        rejeitadosForError(codigo)
          .map((r) => String(r.cco || "").trim())
          .filter(Boolean)
      ),
    ];
  }

  function eligibleCountForError(codigo, fixAction) {
    return rejeitadosForError(codigo).filter((r) => {
      if (!r.cadusu_id) return false;
      const pos = String(r.cadusu_posans || "").trim();
      const situ = String(r.cadusu_situusu || "").trim().toUpperCase();
      if (fixAction === "posans_inclusao") {
        return (
          situ === "ATIVO" && (pos === "8-REINCLUSAO" || pos === "9-RET REATIV")
        );
      }
      // posans_atualizado (3005, 3011, …)
      return pos !== "4-ATUALIZADO";
    }).length;
  }

  function renderRpxErrorCards(data) {
    const items =
      (data.consolidado && data.consolidado.erros) || data.resumo?.por_codigo_erro || [];
    els.rpxErrorsList.classList.remove("hidden");
    els.rpxErrorsList.innerHTML = "";
    if (!items.length) {
      els.rpxErrorsList.innerHTML = `<p class="empty-state show">Nenhuma crítica consolidada.</p>`;
      return;
    }
    for (const item of items) {
      const card = document.createElement("article");
      card.className = `rpx-error-card ${escapeAttr(item.severidade || "media")}`;
      const eligible = item.fixable
        ? eligibleCountForError(item.codigo_erro, item.fix_action)
        : 0;
      const fixBtn = item.fixable
        ? `<div class="rpx-card-actions">
            <button type="button" class="btn warn btn-rpx-fix" data-codigo="${escapeAttr(
              item.codigo_erro
            )}" ${eligible === 0 ? "disabled" : ""}>${escapeAttr(
              item.fix_label || "Aplicar correção"
            )}</button>
            <span class="eligible">${
              eligible === 0
                ? "Já conciliados na cadusu (nada a gravar)"
                : `${fmt(eligible)} elegível(is) na cadusu`
            }</span>
          </div>`
        : "";
      card.innerHTML = `
        <div class="head">
          <span class="code">${escapeAttr(item.codigo_erro)}</span>
          <span class="badge ${escapeAttr(item.severidade || "media")}">${escapeAttr(
            item.severidade || ""
          )}</span>
          <strong>${escapeAttr(item.titulo || "")}</strong>
          <span class="qty">${fmt(item.quantidade || item.quantidadeOcorrenciaErro)} ocorr.</span>
        </div>
        <p class="msg">${escapeAttr(item.mensagem_erro || "")}</p>
        <p class="hint"><strong>Sugestão:</strong> ${escapeAttr(item.sugestao || "")}</p>
        <p class="hint"><strong>Ação cadusu:</strong> ${escapeAttr(item.acao_cadusu || "")}</p>
        ${fixBtn}
      `;
      els.rpxErrorsList.appendChild(card);
    }
  }

  async function applyRpxFix(codigo) {
    if (!rpxData || !codigo) return;
    const ccos = ccosForError(codigo);
    if (!ccos.length) {
      throw new Error(`Nenhum CCO com crítica ${codigo} no arquivo carregado.`);
    }

    setLoading(true, `Pré-visualizando correção ${codigo}…`);
    els.rpxError.classList.add("hidden");
    if (els.rpxOk) els.rpxOk.classList.add("hidden");
    try {
      const preview = await getJson("/api/retorno/fix", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ codigo_erro: codigo, ccos, confirm: false }),
      });
      const d = preview.data;
      const n = d.total_eligible || 0;
      if (!n) {
        throw new Error(
          `Nenhum registro elegível para ${codigo} (já conciliados ou sem match na cadusu).`
        );
      }
      const detail =
        d.confirm_detail || d.summary || "Esta ação grava alteração na cadusu.";
      const ok = window.confirm(
        `Confirma UPDATE em ${n} registro(s) da cadusu?\n\n` +
          `${d.label}\nCódigo ANS: ${codigo}\n\n${detail}`
      );
      if (!ok) return;

      setLoading(true, `Aplicando correção ${codigo}…`);
      const applied = await getJson("/api/retorno/fix", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ codigo_erro: codigo, ccos, confirm: true }),
      });
      const a = applied.data;
      const updatedCcos = new Set(
        (a.cco_refs || [])
          .map((c) => String(c || "").trim())
          .filter(Boolean)
      );
      // fallback: se o apply ainda devolveu codcco nas rows
      for (const r of a.rows || []) {
        const c = String(r.codcco || "").trim();
        if (c) updatedCcos.add(c);
      }
      const posNovo = a.posans_novo || "4-ATUALIZADO";
      for (const row of rpxData.rejeitados || []) {
        if (updatedCcos.has(String(row.cco || "").trim())) {
          row.cadusu_posans = posNovo;
          if (a.cleared_cco) {
            row.cadusu_codusu = row.cadusu_codusu;
          }
        }
      }
      renderRpxErrorCards(rpxData);
      renderRpxTable();
      if (els.rpxOk) {
        els.rpxOk.textContent =
          `Correção ${codigo} aplicada: ${fmt(a.updated)} de ${fmt(a.requested)} ` +
          `registro(s) atualizado(s) (${a.label}).`;
        els.rpxOk.classList.remove("hidden");
      }
      await loadDashboard();
    } finally {
      setLoading(false);
    }
  }

  function fillRpxFilters(data) {
    const codes = (data.resumo?.por_codigo_erro || []).map((i) => i.codigo_erro);
    const movs = (data.resumo?.por_movimento || []).map((i) => i.tipo_movimento);
    const prevCode = els.rpxFilterCode.value;
    const prevMov = els.rpxFilterMov.value;
    els.rpxFilterCode.innerHTML = `<option value="">Todos</option>`;
    for (const c of codes) {
      const opt = document.createElement("option");
      opt.value = c;
      opt.textContent = c;
      els.rpxFilterCode.appendChild(opt);
    }
    els.rpxFilterMov.innerHTML = `<option value="">Todos</option>`;
    for (const m of movs) {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      els.rpxFilterMov.appendChild(opt);
    }
    if (codes.includes(prevCode)) els.rpxFilterCode.value = prevCode;
    if (movs.includes(prevMov)) els.rpxFilterMov.value = prevMov;
  }

  function filteredRpxRows() {
    if (!rpxData) return [];
    const code = els.rpxFilterCode.value;
    const mov = els.rpxFilterMov.value;
    return (rpxData.rejeitados || []).filter((r) => {
      if (code && r.codigo_erro !== code) return false;
      if (mov && r.tipo_movimento !== mov) return false;
      return true;
    });
  }

  function renderRpxTable() {
    const rows = filteredRpxRows();
    const columns = [
      "codigo_erro",
      "tipo_movimento",
      "cco",
      "codigo_beneficiario",
      "descricao_campo",
      "valor_campo",
      "mensagem_erro",
      "sugestao",
      "acao_cadusu",
      "cadusu_id",
      "cadusu_nome",
      "cadusu_situusu",
      "cadusu_posans",
    ];
    els.rpxTableHead.innerHTML = "";
    els.rpxTableBody.innerHTML = "";
    els.rpxTableWrap.classList.remove("hidden");

    const trh = document.createElement("tr");
    for (const col of columns) {
      const th = document.createElement("th");
      th.textContent = col;
      trh.appendChild(th);
    }
    els.rpxTableHead.appendChild(trh);

    for (const row of rows) {
      const tr = document.createElement("tr");
      if (row.severidade === "critica") tr.classList.add("row-critica");
      for (const col of columns) {
        const td = document.createElement("td");
        const val = row[col];
        td.textContent = val === null || val === undefined ? "" : String(val);
        if (col === "sugestao" || col === "acao_cadusu" || col === "mensagem_erro") {
          td.title = td.textContent;
        }
        tr.appendChild(td);
      }
      els.rpxTableBody.appendChild(tr);
    }

    const total = rpxData?.resumo?.total_rejeitados || 0;
    const truncated = rpxData?.rejeitados_truncated
      ? ` · exibindo até ${fmt((rpxData.rejeitados || []).length)} carregados`
      : "";
    els.rpxTableMeta.textContent = `${fmt(rows.length)} na tabela · ${fmt(
      total
    )} rejeitados no arquivo${truncated}`;
  }

  async function parseRpx(ev) {
    if (ev) ev.preventDefault();
    els.rpxError.classList.add("hidden");
    if (els.rpxOk) els.rpxOk.classList.add("hidden");
    setLoading(true, "Lendo arquivo retorno .RPX…");
    try {
      const fd = new FormData();
      const file = els.rpxFile?.files?.[0];
      const path = (els.rpxPath?.value || "").trim();
      if (file) fd.append("file", file);
      else if (path) fd.append("path", path);
      else throw new Error("Informe o caminho do .RPX ou selecione um arquivo.");

      const res = await fetch("/api/retorno/parse", { method: "POST", body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) {
        throw new Error(data.error || "Falha ao ler o arquivo retorno");
      }
      rpxData = data.data;
      renderRpxSummary(rpxData);
      renderRpxErrorCards(rpxData);
      fillRpxFilters(rpxData);
      renderRpxTable();
    } catch (err) {
      rpxData = null;
      els.rpxSummary.classList.add("hidden");
      els.rpxErrorsList.classList.add("hidden");
      els.rpxTableWrap.classList.add("hidden");
      els.rpxError.textContent = err.message;
      els.rpxError.classList.remove("hidden");
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
  if (els.rpxForm) els.rpxForm.addEventListener("submit", parseRpx);
  if (els.rpxFilterCode) els.rpxFilterCode.addEventListener("change", renderRpxTable);
  if (els.rpxFilterMov) els.rpxFilterMov.addEventListener("change", renderRpxTable);
  if (els.rpxErrorsList) {
    els.rpxErrorsList.addEventListener("click", async (ev) => {
      const btn = ev.target.closest(".btn-rpx-fix");
      if (!btn) return;
      try {
        await applyRpxFix(btn.getAttribute("data-codigo"));
      } catch (err) {
        els.rpxError.textContent = err.message;
        els.rpxError.classList.remove("hidden");
        if (els.rpxOk) els.rpxOk.classList.add("hidden");
        setLoading(false);
      }
    });
  }

  loadSummary();
})();
