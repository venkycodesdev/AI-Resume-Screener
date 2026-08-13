document.addEventListener("DOMContentLoaded", () => {
    const menuToggle = document.getElementById("menuToggle");
    const navLinks = document.getElementById("navLinks");
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
        link.addEventListener("click", () => {
            closeMobileMenu();
        });
    });


    document.addEventListener("click", (event) => {
        const clickedInsideNavbar =
            event.target.closest(".navbar");

        if (!clickedInsideNavbar) {
            closeMobileMenu();
        }
    });


    window.addEventListener("resize", () => {
        if (window.innerWidth > 850) {
            closeMobileMenu();
        }
    });


    const observerOptions = {
        root: null,
        rootMargin: "-35% 0px -55% 0px",
        threshold: 0
    };


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
        observerOptions
    );


    sections.forEach((section) => {
        sectionObserver.observe(section);
    });
});