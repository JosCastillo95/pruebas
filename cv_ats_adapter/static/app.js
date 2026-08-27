const cvEditor = document.getElementById("cv-maestro-editor");
const cvStatus = document.getElementById("cv-maestro-status");
const btnGuardarCv = document.getElementById("btn-guardar-cv");

const vacanteInput = document.getElementById("vacante-input");
const chkGancho = document.getElementById("chk-gancho");
const btnProcesar = document.getElementById("btn-procesar");
const procesarStatus = document.getElementById("procesar-status");

const panelResultado = document.getElementById("panel-resultado");
const resultadoBloqueado = document.getElementById("resultado-bloqueado");
const resultadoOk = document.getElementById("resultado-ok");

async function cargarCvMaestro() {
  const res = await fetch("/api/cv_maestro");
  const data = await res.json();
  cvEditor.value = JSON.stringify(data, null, 2);
}

btnGuardarCv.addEventListener("click", async () => {
  cvStatus.textContent = "Guardando...";
  let parsed;
  try {
    parsed = JSON.parse(cvEditor.value);
  } catch (e) {
    cvStatus.textContent = `JSON inválido: ${e.message}`;
    return;
  }
  const res = await fetch("/api/cv_maestro", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(parsed),
  });
  if (res.ok) {
    cvStatus.textContent = "Guardado.";
  } else {
    const err = await res.json();
    cvStatus.textContent = `Error: ${err.error || res.statusText}`;
  }
  setTimeout(() => (cvStatus.textContent = ""), 4000);
});

function renderList(elId, items, formatter) {
  const el = document.getElementById(elId);
  el.innerHTML = "";
  if (!items || items.length === 0) {
    el.innerHTML = "<li class='hint'>Ninguno.</li>";
    return;
  }
  for (const item of items) {
    const li = document.createElement("li");
    li.textContent = formatter ? formatter(item) : String(item);
    el.appendChild(li);
  }
}

function renderDiscrepancias(elId, discrepancias, claseExtra) {
  const el = document.getElementById(elId);
  el.innerHTML = "";
  if (!discrepancias || discrepancias.length === 0) {
    el.innerHTML = "<p class='hint'>Ninguna.</p>";
    return;
  }
  for (const d of discrepancias) {
    const div = document.createElement("div");
    div.className = `discrepancy-item ${claseExtra || ""}`;
    const valor = d.valor || d.fragmento_cv_adaptado || "";
    const explicacion = d.explicacion || d.respaldo_cv_maestro || "";
    div.innerHTML = `<strong>[Capa ${d.capa || "?"} · ${d.tipo || d.clasificacion || ""}]</strong> ${valor}<br/><span class="hint">${explicacion}</span>`;
    el.appendChild(div);
  }
}

btnProcesar.addEventListener("click", async () => {
  const vacancy_text = vacanteInput.value.trim();
  if (!vacancy_text) {
    procesarStatus.textContent = "Pega el texto de la vacante primero.";
    return;
  }

  btnProcesar.disabled = true;
  procesarStatus.textContent = "Procesando (análisis → adaptación → 4 fases → validación)...";
  panelResultado.hidden = true;
  resultadoBloqueado.hidden = true;
  resultadoOk.hidden = true;

  try {
    const res = await fetch("/api/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        vacancy_text,
        generar_variante_gancho: chkGancho.checked,
      }),
    });
    const data = await res.json();

    if (!res.ok) {
      procesarStatus.textContent = `Error: ${data.error || res.statusText}`;
      return;
    }

    panelResultado.hidden = false;

    if (data.detenido) {
      resultadoBloqueado.hidden = false;
      document.getElementById("motivo-detencion").textContent = data.motivo_detencion || "Proceso detenido.";
      renderDiscrepancias("discrepancias-criticas", data.discrepancias_criticas, "");
    } else {
      resultadoOk.hidden = false;

      const badge = document.getElementById("score-badge");
      badge.textContent = data.puntaje_compatibilidad ?? "--";
      document.getElementById("ciclos-info").textContent =
        `Ciclos de reintento usados: ${data.ciclos_reintento ?? 0}`;

      const linkDocx = document.getElementById("link-docx");
      const linkPdf = document.getElementById("link-pdf");
      if (data.docx_filename) {
        linkDocx.href = `/api/download/${encodeURIComponent(data.docx_filename)}`;
        linkDocx.hidden = false;
      }
      if (data.pdf_filename) {
        linkPdf.href = `/api/download/${encodeURIComponent(data.pdf_filename)}`;
        linkPdf.hidden = false;
      }
      const pdfErrorEl = document.getElementById("pdf-error");
      if (data.pdf_error) {
        pdfErrorEl.hidden = false;
        pdfErrorEl.textContent = data.pdf_error;
      } else {
        pdfErrorEl.hidden = true;
      }

      const ganchoBlock = document.getElementById("gancho-block");
      if (data.perfil_resumen_variante_gancho) {
        ganchoBlock.hidden = false;
        document.getElementById("gancho-texto").textContent = data.perfil_resumen_variante_gancho;
        document.getElementById("gancho-advertencia").textContent = data.advertencia_tono_gancho || "";
        document.getElementById("gancho-suave").textContent = data.version_suavizada_gancho || "";
      } else {
        ganchoBlock.hidden = true;
      }

      renderDiscrepancias("discrepancias-matiz", data.discrepancias_matiz, "matiz");
      renderList("gaps-detectados", data.gaps_detectados);
      renderList("campos-incompletos", data.campos_incompletos_relevantes);
      renderList(
        "secciones-riesgo",
        data.secciones_en_riesgo,
        (s) => `${s.seccion}: ${s.razon}`
      );

      const señalesEl = document.getElementById("señales-info");
      señalesEl.innerHTML = `
        <p><strong>Detectadas:</strong> ${(data.señales_detectadas || []).map((s) => s.señal).join("; ") || "Ninguna"}</p>
        <p><strong>Resueltas:</strong> ${(data.señales_resueltas || []).join("; ") || "Ninguna"}</p>
        <p><strong>No resueltas por falta de dato:</strong> ${(data.señales_no_resueltas_por_falta_de_dato || []).join("; ") || "Ninguna"}</p>
      `;
    }
  } catch (err) {
    procesarStatus.textContent = `Error inesperado: ${err.message}`;
  } finally {
    btnProcesar.disabled = false;
    procesarStatus.textContent = "";
  }
});

cargarCvMaestro();
