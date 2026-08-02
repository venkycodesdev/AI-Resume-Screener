document.addEventListener("DOMContentLoaded", () => {
    const uploadForm = document.querySelector(".upload-form");
    const fileInput = document.querySelector("#resume");
    const submitButton = document.querySelector(
        ".upload-submit-button"
    );

    const successMessage = document.querySelector(
        ".upload-message.success-message"
    );

    const resultSelectors = [
        ".analysis-dashboard",
        ".score-section",
        ".matching-section",
        ".missing-section",
        ".skill-gap-section",
        ".ats-rating-section",
        ".resume-strength-section",
        ".suggestions-section",
        ".final-recommendation-section",
        ".extracted-text-section"
    ];

    const resultSections = document.querySelectorAll(
        resultSelectors.join(",")
    );


    /*
     * Show the selected resume filename.
     */
    if (fileInput) {
        const selectedFileInfo = document.createElement("p");

        selectedFileInfo.className = "selected-file-info";
        selectedFileInfo.textContent = "No resume selected.";

        fileInput.insertAdjacentElement(
            "afterend",
            selectedFileInfo
        );


        fileInput.addEventListener("change", () => {
            const selectedFile = fileInput.files[0];

            if (!selectedFile) {
                selectedFileInfo.textContent =
                    "No resume selected.";

                selectedFileInfo.classList.remove(
                    "valid-file",
                    "invalid-file"
                );

                return;
            }

            const fileName = selectedFile.name;
            const extension = fileName
                .split(".")
                .pop()
                .toLowerCase();

            const allowedExtensions = ["pdf", "docx"];

            if (!allowedExtensions.includes(extension)) {
                selectedFileInfo.textContent =
                    "Invalid file. Please choose a PDF or DOCX resume.";

                selectedFileInfo.classList.add("invalid-file");
                selectedFileInfo.classList.remove("valid-file");

                fileInput.value = "";

                return;
            }

            selectedFileInfo.textContent =
                `Selected resume: ${fileName}`;

            selectedFileInfo.classList.add("valid-file");
            selectedFileInfo.classList.remove("invalid-file");
        });
    }


    /*
     * Show a loading state while Flask analyzes the resume.
     */
    if (uploadForm && submitButton) {
        uploadForm.addEventListener("submit", () => {
            submitButton.disabled = true;
            submitButton.classList.add("button-loading");

            submitButton.innerHTML = `
                <span class="loading-spinner"></span>
                Analyzing Resume...
            `;
        });
    }


    /*
     * Automatically move to the results after analysis.
     */
    if (successMessage) {
        window.setTimeout(() => {
            successMessage.scrollIntoView({
                behavior: "smooth",
                block: "start"
            });
        }, 300);
    }


    /*
     * Animate result sections when they enter the screen.
     */
    if ("IntersectionObserver" in window) {
        const sectionObserver = new IntersectionObserver(
            (entries, observer) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting) {
                        entry.target.classList.add(
                            "section-visible"
                        );

                        observer.unobserve(entry.target);
                    }
                });
            },
            {
                threshold: 0.12
            }
        );

        resultSections.forEach((section) => {
            section.classList.add("reveal-section");
            sectionObserver.observe(section);
        });
    } else {
        resultSections.forEach((section) => {
            section.classList.add("section-visible");
        });
    }
});