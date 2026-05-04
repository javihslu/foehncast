(function () {
    const MERMAID_MODULE_URL = "https://unpkg.com/mermaid@10.4.0/dist/mermaid.esm.min.mjs";
    const MERMAID_CONFIG = {
        startOnLoad: false,
        securityLevel: "loose",
        theme: "neutral",
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

    async function renderMermaid(root) {
        const nodes = findPendingDiagrams(root);
        if (!nodes.length) {
            return;
        }

        const mermaid = await loadMermaid();
        mermaid.initialize(MERMAID_CONFIG);
        await mermaid.run({ nodes });
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
