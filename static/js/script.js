document.addEventListener("DOMContentLoaded", () => {
    const menuToggle = document.getElementById("menuToggle");
    const navLinks = document.getElementById("navLinks");

    if (!menuToggle || !navLinks) {
        return;
    }

    const navigationLinks = document.querySelectorAll(".nav-link");
    const sections = document.querySelectorAll(
        "#home, #features, #about, #developer, #contact"
    );

    const closeMobileMenu = () => {
        menuToggle.classList.remove("active");
        navLinks.classList.remove("open");
        document.body.classList.remove("menu-open");
        menuToggle.setAttribute("aria-expanded", "false");
        menuToggle.setAttribute(
            "aria-label",
            "Open navigation menu"
        );
    };

    menuToggle.addEventListener("click", () => {
        const menuIsOpen = navLinks.classList.toggle("open");

        menuToggle.classList.toggle("active", menuIsOpen);
        document.body.classList.toggle("menu-open", menuIsOpen);
        menuToggle.setAttribute(
            "aria-expanded",
            String(menuIsOpen)
        );
        menuToggle.setAttribute(
            "aria-label",
            menuIsOpen
                ? "Close navigation menu"
                : "Open navigation menu"
        );
    });

    navigationLinks.forEach((link) => {
        link.addEventListener("click", closeMobileMenu);
    });

    document.addEventListener("click", (event) => {
        if (!event.target.closest(".navbar")) {
            closeMobileMenu();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeMobileMenu();
        }
    });

    window.addEventListener("resize", () => {
        if (window.innerWidth > 850) {
            closeMobileMenu();
        }
    });

    if (!("IntersectionObserver" in window)) {
        return;
    }

    const sectionObserver = new IntersectionObserver(
        (entries) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) {
                    return;
                }

                navigationLinks.forEach((link) => {
                    link.classList.remove("active");
                });

                const activeLink = document.querySelector(
                    `.nav-link[href="#${entry.target.id}"]`
                );

                if (activeLink) {
                    activeLink.classList.add("active");
                }
            });
        },
        {
            root: null,
            rootMargin: "-35% 0px -55% 0px",
            threshold: 0,
        }
    );

    sections.forEach((section) => {
        sectionObserver.observe(section);
    });
});