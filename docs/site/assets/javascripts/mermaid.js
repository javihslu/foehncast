(function () {
    const MERMAID_MODULE_URL = "https://unpkg.com/mermaid@10.4.0/dist/mermaid.esm.min.mjs";
    const MERMAID_CONFIG = {
        startOnLoad: false,
        htmlLabels: true,
        securityLevel: "loose",
        theme: "base",
        fontFamily: "Manrope, system-ui, sans-serif",
        themeVariables: {
            fontFamily: "Manrope, sans-serif",
            fontSize: "16px",
            primaryColor: "#e0f2f1",
            primaryBorderColor: "#00897b",
            primaryTextColor: "#0f2530",
            lineColor: "#546e7a",
            secondaryColor: "#fff3e0",
            secondaryBorderColor: "#ff7a26",
            tertiaryColor: "#fafafa",
            tertiaryBorderColor: "#0f766e",
            clusterBkg: "rgba(15, 118, 110, 0.06)",
            clusterBorder: "rgba(15, 118, 110, 0.35)",
            titleColor: "#07252a",
            edgeLabelBackground: "#ffffff",
        },
        flowchart: {
            curve: "basis",
            nodeSpacing: 45,
            rankSpacing: 55,
            padding: 12,
        },
    };

    let mermaidPromise;

    function loadMermaid() {
        if (!mermaidPromise) {
            mermaidPromise = import(MERMAID_MODULE_URL).then((module) => module.default);
        }
        return mermaidPromise;
    }

    function normalizeLegacyBlocks(root) {
        const selectors = [
            "pre.mermaid code",
            "pre code.mermaid",
            "pre code.language-mermaid",
        ];

        for (const codeBlock of root.querySelectorAll(selectors.join(","))) {
            const preBlock = codeBlock.closest("pre");
            if (!preBlock) {
                continue;
            }

            const container = document.createElement("div");
            container.className = "mermaid";
            container.textContent = codeBlock.textContent || "";
            preBlock.replaceWith(container);
        }
    }

    function findPendingDiagrams(root) {
        normalizeLegacyBlocks(root);
        return Array.from(root.querySelectorAll("div.mermaid")).filter((node) => {
            return node.dataset.processed !== "true" && node.textContent.trim() !== "";
        });
    }

    function parseSvgNumber(value) {
        const number = Number.parseFloat(value || "0");
        return Number.isFinite(number) ? number : 0;
    }

    function adjustClusterLabels(root) {
        for (const svg of root.querySelectorAll(".mermaid svg")) {
            for (const cluster of svg.querySelectorAll("g.cluster")) {
                const rect = cluster.querySelector("rect");
                const label = cluster.querySelector("g.cluster-label");
                const foreignObject = label?.querySelector("foreignObject");
                const container = foreignObject?.firstElementChild;
                const nodeLabel = container?.querySelector(".nodeLabel");

                if (!rect || !label || !foreignObject || !container || !nodeLabel) {
                    continue;
                }

                const rectX = parseSvgNumber(rect.getAttribute("x"));
                const rectY = parseSvgNumber(rect.getAttribute("y"));
                const rectWidth = parseSvgNumber(rect.getAttribute("width"));
                const padding = Math.max(10, Math.min(18, rectWidth * 0.05));
                const labelWidth = Math.max(48, rectWidth - (padding * 2));

                label.setAttribute("transform", `translate(${rectX + padding}, ${rectY})`);
                foreignObject.setAttribute("width", String(labelWidth));
                container.style.display = "block";
                container.style.width = `${labelWidth}px`;
                container.style.whiteSpace = "nowrap";
                container.style.textAlign = "left";
                nodeLabel.style.display = "block";
                nodeLabel.style.width = "100%";
                nodeLabel.style.textAlign = "left";
            }
        }
    }

    async function renderMermaid(root) {
        const nodes = findPendingDiagrams(root);
        if (!nodes.length) {
            return;
        }

        const mermaid = await loadMermaid();
        mermaid.initialize(MERMAID_CONFIG);
        await mermaid.run({ nodes });
        adjustClusterLabels(root);
    }

    function scheduleRender(root) {
        const run = () => {
            renderMermaid(root).catch((error) => {
                console.error("FoehnCast Mermaid render failed", error);
            });
        };

        if (typeof window.requestAnimationFrame === "function") {
            window.requestAnimationFrame(run);
        } else {
            window.setTimeout(run, 0);
        }
    }

    function attachMaterialHook() {
        if (!window.document$ || typeof window.document$.subscribe !== "function") {
            return false;
        }

        window.document$.subscribe(() => {
            scheduleRender(document);
        });
        return true;
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => {
            scheduleRender(document);
        }, { once: true });
    } else {
        scheduleRender(document);
    }

    if (!attachMaterialHook()) {
        let attempts = 0;
        const intervalId = window.setInterval(() => {
            attempts += 1;
            if (attachMaterialHook() || attempts >= 20) {
                window.clearInterval(intervalId);
            }
        }, 100);
    }
})();
