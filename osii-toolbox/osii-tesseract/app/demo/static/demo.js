const state = {
    docId: null,
    pages: [],
    regionSetId: null,
    debounceTimer: null,
    defaultsLoaded: false
};

function byId(id) {
    return document.getElementById(id);
}

function setStatus(message) {
    byId("uploadStatus").textContent = message || "";
}

function updateRangeValue(id, formatter = null) {
    const input = byId(id);
    const output = byId(id + "Value");
    if (input && output) {
        output.textContent = formatter ? formatter(input.value) : input.value;
    }
}

function getDetectionParams() {
    return {
        threshold_mode: byId("thresholdMode").value,
        blur_kernel: parseInt(byId("blurKernel").value, 10),
        adaptive_block_size: parseInt(byId("adaptiveBlockSize").value, 10),
        adaptive_c: parseInt(byId("adaptiveC").value, 10),
        open_kernel_w: parseInt(byId("openKernelW").value, 10),
        open_kernel_h: parseInt(byId("openKernelH").value, 10),
        dilate_kernel_w: parseInt(byId("dilateKernelW").value, 10),
        dilate_kernel_h: parseInt(byId("dilateKernelH").value, 10),
        dilate_iterations: parseInt(byId("dilateIterations").value, 10),
        min_contour_area: parseInt(byId("minContourArea").value, 10),
        min_width: parseInt(byId("minWidth").value, 10),
        min_height: parseInt(byId("minHeight").value, 10),
        bbox_padding: parseInt(byId("bboxPadding").value, 10),
        max_regions: parseInt(byId("maxRegions").value, 10)
    };
}

function getRecognitionParams() {
    return {
        language: byId("language").value,
        tesseract_psm: byId("tesseractPsm").value,
        confidence_threshold: parseFloat(byId("confidenceThreshold").value)
    };
}

function getSelectedPage() {
    return parseInt(byId("pageSelect").value, 10);
}

function setPreview(id, url) {
    const img = byId("preview-" + id);
    if (!img) {
        return;
    }
    if (url) {
        img.src = url + "?t=" + Date.now();
    } else {
        img.removeAttribute("src");
    }
}

function renderDetectStats(stats) {
    if (!stats) {
        byId("detectStats").textContent = "";
        return;
    }

    byId("detectStats").textContent =
        `Detected regions: ${stats.num_regions ?? 0} | ` +
        `Page: ${stats.page_width ?? 0} x ${stats.page_height ?? 0}`;
}

function renderOCRStats(stats) {
    if (!stats) {
        byId("ocrStats").textContent = "";
        return;
    }

    byId("ocrStats").textContent =
        `OCR results: ${stats.num_ocr_results ?? 0} | ` +
        `Regions used: ${stats.num_regions ?? 0}`;
}

function renderResults(results) {
    const tbody = byId("resultsTable").querySelector("tbody");
    tbody.innerHTML = "";

    (results || []).forEach((item, index) => {
        const row = document.createElement("tr");

        const idx = document.createElement("td");
        idx.textContent = String(index + 1);

        const text = document.createElement("td");
        text.textContent = item.text || "";

        const conf = document.createElement("td");
        conf.textContent = typeof item.confidence === "number"
            ? item.confidence.toFixed(3)
            : "";

        const bbox = document.createElement("td");
        bbox.textContent = JSON.stringify(item.bbox || []);

        row.appendChild(idx);
        row.appendChild(text);
        row.appendChild(conf);
        row.appendChild(bbox);
        tbody.appendChild(row);
    });
}

function populatePages(pages) {
    const select = byId("pageSelect");
    select.innerHTML = "";

    pages.forEach((page) => {
        const option = document.createElement("option");
        option.value = page.page;
        option.textContent = `Page ${page.page}`;
        select.appendChild(option);
    });
}

function applyDefaults(defaults) {
    const detection = defaults.detection || {};
    const recognition = defaults.recognition || {};

    if (detection.threshold_mode) byId("thresholdMode").value = detection.threshold_mode;
    if (detection.blur_kernel != null) byId("blurKernel").value = detection.blur_kernel;
    if (detection.adaptive_block_size != null) byId("adaptiveBlockSize").value = detection.adaptive_block_size;
    if (detection.adaptive_c != null) byId("adaptiveC").value = detection.adaptive_c;
    if (detection.open_kernel_w != null) byId("openKernelW").value = detection.open_kernel_w;
    if (detection.open_kernel_h != null) byId("openKernelH").value = detection.open_kernel_h;
    if (detection.dilate_kernel_w != null) byId("dilateKernelW").value = detection.dilate_kernel_w;
    if (detection.dilate_kernel_h != null) byId("dilateKernelH").value = detection.dilate_kernel_h;
    if (detection.dilate_iterations != null) byId("dilateIterations").value = detection.dilate_iterations;
    if (detection.min_contour_area != null) byId("minContourArea").value = detection.min_contour_area;
    if (detection.min_width != null) byId("minWidth").value = detection.min_width;
    if (detection.min_height != null) byId("minHeight").value = detection.min_height;
    if (detection.bbox_padding != null) byId("bboxPadding").value = detection.bbox_padding;
    if (detection.max_regions != null) byId("maxRegions").value = detection.max_regions;

    if (recognition.language) byId("language").value = recognition.language;
    if (recognition.tesseract_psm) byId("tesseractPsm").value = recognition.tesseract_psm;
    if (recognition.confidence_threshold != null) {
        byId("confidenceThreshold").value = recognition.confidence_threshold;
    }

    updateAllDisplayedValues();
}

function updateAllDisplayedValues() {
    [
        "blurKernel",
        "adaptiveBlockSize",
        "adaptiveC",
        "openKernelW",
        "openKernelH",
        "dilateKernelW",
        "dilateKernelH",
        "dilateIterations",
        "minContourArea",
        "minWidth",
        "minHeight",
        "bboxPadding",
        "maxRegions"
    ].forEach((id) => updateRangeValue(id));

    updateRangeValue("confidenceThreshold", (v) => Number(v).toFixed(2));
}

async function loadDefaults() {
    try {
        const response = await fetch("/demo/config");
        const data = await response.json();
        if (response.ok && data.defaults) {
            applyDefaults(data.defaults);
            state.defaultsLoaded = true;
        }
    } catch (error) {
        console.error("Failed to load defaults", error);
    }
}

async function uploadFile() {
    const input = byId("fileInput");
    const file = input.files[0];
    if (!file) {
        setStatus("Select a file first.");
        return;
    }

    const formData = new FormData();
    formData.append("file", file);

    setStatus("Uploading...");
    try {
        const response = await fetch("/demo/upload", {
            method: "POST",
            body: formData
        });

        const data = await response.json();
        if (!response.ok) {
            setStatus(data.error || "Upload failed.");
            return;
        }

        state.docId = data.doc_id;
        state.pages = data.pages || [];
        state.regionSetId = null;

        populatePages(state.pages);

        if (state.pages.length > 0) {
            const firstPage = state.pages[0];
            setPreview("original", firstPage.image_url);
        }

        setStatus(`Uploaded ${data.page_count} page(s).`);
        await detectRegions();
    } catch (error) {
        setStatus("Upload failed.");
    }
}

async function detectRegions() {
    if (!state.docId) {
        return;
    }

    const page = getSelectedPage();
    if (!page) {
        return;
    }

    const payload = {
        doc_id: state.docId,
        page: page,
        params: getDetectionParams()
    };

    setStatus("Detecting regions...");
    try {
        const response = await fetch("/demo/detect", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        if (!response.ok) {
            setStatus(data.error || "Detect failed.");
            return;
        }

        state.regionSetId = data.region_set_id;

        setPreview("original", data.images["original"]);
        setPreview("gray", data.images["gray"]);
        setPreview("binary", data.images["binary"]);
        setPreview("cleaned", data.images["cleaned"]);
        setPreview("dilated", data.images["dilated"]);
        setPreview("overlay", data.images["overlay"]);

        renderDetectStats(data.stats);
        renderOCRStats(null);
        renderResults([]);
        setPreview("ocr-overlay", "");
        setStatus(`Detection complete. Region set: ${state.regionSetId}`);
    } catch (error) {
        setStatus("Detect failed.");
    }
}

async function runOCR() {
    if (!state.docId || !state.regionSetId) {
        setStatus("Run detection first.");
        return;
    }

    const page = getSelectedPage();
    if (!page) {
        return;
    }

    const payload = {
        doc_id: state.docId,
        page: page,
        region_set_id: state.regionSetId,
        detection_params: getDetectionParams(),
        recognition_params: getRecognitionParams()
    };

    setStatus("Running OCR...");
    try {
        const response = await fetch("/demo/ocr", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        if (!response.ok) {
            setStatus(data.error || "OCR failed.");
            return;
        }

        if (data.images && data.images["overlay"]) {
            setPreview("ocr-overlay", data.images["overlay"]);
        }

        renderOCRStats(data.stats);
        renderResults(data.results);
        setStatus("OCR complete.");
    } catch (error) {
        setStatus("OCR failed.");
    }
}

function scheduleDetect() {
    if (!byId("autoDetect").checked) {
        return;
    }

    if (state.debounceTimer) {
        window.clearTimeout(state.debounceTimer);
    }

    state.debounceTimer = window.setTimeout(() => {
        detectRegions();
    }, 300);
}

function initializeControls() {
    const integerRanges = [
        "blurKernel",
        "adaptiveBlockSize",
        "adaptiveC",
        "openKernelW",
        "openKernelH",
        "dilateKernelW",
        "dilateKernelH",
        "dilateIterations",
        "minContourArea",
        "minWidth",
        "minHeight",
        "bboxPadding",
        "maxRegions"
    ];

    integerRanges.forEach((id) => {
        byId(id).addEventListener("input", () => {
            updateRangeValue(id);
            scheduleDetect();
        });
    });

    byId("confidenceThreshold").addEventListener("input", () => {
        updateRangeValue("confidenceThreshold", (v) => Number(v).toFixed(2));
    });

    byId("thresholdMode").addEventListener("change", scheduleDetect);
    byId("pageSelect").addEventListener("change", detectRegions);
    byId("uploadButton").addEventListener("click", uploadFile);
    byId("detectButton").addEventListener("click", detectRegions);
    byId("ocrButton").addEventListener("click", runOCR);

    updateAllDisplayedValues();
}

window.addEventListener("DOMContentLoaded", async () => {
    initializeControls();
    await loadDefaults();
});