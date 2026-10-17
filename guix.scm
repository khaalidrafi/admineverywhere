;;; admincraft — Guix package definition
;;;
;;; Written against the Guix manual ("Defining Packages" + "Build Systems").
;;; The official cargo-build-system expects every crate as a separate Guix
;;; source input and even deletes Cargo.lock — wrong shape for a ~600-crate
;;; Tauri 2 dependency tree. We therefore use the classic gnu-build-system
;;; recipe with a vendor directory prepared ahead of the build:
;;;
;;;   1. (cd app && npm ci && npm run build)      ; web bundle -> app/dist
;;;   2. (cd app/src-tauri && cargo vendor vendor ; vendored crates
;;;        > .cargo/config.toml)
;;;   3. guix build -f guix.scm                   ; fully offline (--frozen)
;;;
;;; The parked demo-CI (`.github/workflows/build-demo.yml.disabled`, `guix`
;;; job) runs exactly these steps, so the vendored source never has to be committed to the repo.

(use-modules (guix packages)
             (guix build-system gnu)
             (guix gexp)
             ((guix licenses) #:prefix license:)
             (gnu packages glib)
             (gnu packages gnome)
             (gnu packages gtk)
             (gnu packages webkit)
             (gnu packages pkg-config)
             (gnu packages rust)
             (ice-9 regex))

(define %source
  ;; Repo checkout including the prebuilt web bundle (app/dist) and the
  ;; vendored crates (app/src-tauri/vendor) — everything except bulky
  ;; build caches.
  (local-file "." "admincraft-checkout"
              #:recursive? #t
              #:select? (lambda (file stat)
                          (not (or (string-contains file "node_modules")
                                   (string-contains file "src-tauri/target")
                                   (string-contains file "src-tauri/gen")
                                   ;; Match a whole ".git" path component only
                                   ;; (never ".github", ".gitignore", …).
                                   ;; Vendored crates ship those files and
                                   ;; cargo's .cargo-checksum.json lists them,
                                   ;; so a loose substring match silently
                                   ;; breaks the --frozen checksum check
                                   ;; (first seen 2026-10-17: anyhow's
                                   ;; .github/FUNDING.yml, run 38992031791).
                                   (string-match "(^|/)\\.git(/|$)" file)
                                   (string-contains file ".venv")
                                   (string-contains file "frontend-dist")
                                   (string-contains file "guix-install")
                                   (string-contains file "__pycache__")
                                   (string-contains file ".pytest_cache")
                                   ;; Root "result" symlink (nix) — again an
                                   ;; exact component, not a prefix that
                                   ;; would also eat "results/…" paths.
                                   (string-match "(^|/)result(/|$)" file)
                                   (string-contains file ".tar.gz"))))))

(define-public admincraft
  (package
    (name "admincraft")
    (version "0.1.0")
    (source %source)
    (build-system gnu-build-system)
    (arguments
     (list
      #:tests? #f                    ; UI app — tested by the app test suites
      #:phases
      #~(modify-phases %standard-phases
          (delete 'configure)        ; no autotools
          (replace 'build
            (lambda _
              (setenv "CARGO_HOME" (getcwd))
              ;; Documented Tauri env override; frontendDist accepts an
              ;; absolute path, so the source stays unpatched.
              (setenv "TAURI_CONFIG"
                      (string-append
                       "{\"build\":{\"frontendDist\":\""
                       (getcwd) "/app/dist\"}}"))
              ;; cargo discovers .cargo/config.toml by walking up from the
              ;; CWD (not the manifest path), so build from app/src-tauri —
              ;; that's where `cargo vendor` put .cargo/config.toml.
              (with-directory-excursion "app/src-tauri"
                (invoke "cargo" "build"
                        "--release" "--offline" "--frozen"))))
          (replace 'install
            (lambda* (#:key outputs #:allow-other-keys)
              (let ((out (assoc-ref outputs "out")))
                (install-file "app/src-tauri/target/release/admincraft"
                              (string-append out "/bin"))
                (let ((icons (string-append out "/share/icons/hicolor/128x128/apps"))
                      (apps (string-append out "/share/applications")))
                  (mkdir-p icons)
                  (install-file "app/src-tauri/icons/128x128.png"
                                (string-append icons "/admincraft.png"))
                  (mkdir-p apps)
                  (call-with-output-file
                      (string-append apps "/com.khaalidrafi.admincraft.desktop")
                    (lambda (port)
                      (format port
                              "[Desktop Entry]~%
Type=Application~%
Name=Admincraft~%
Comment=Branded schema-driven admin for Django REST Framework APIs~%
Exec=admincraft~%
Icon=admincraft~%
Categories=Development;Utility;~%")))))))
          (add-after 'install 'wrap-runtime
            (lambda* (#:key inputs outputs #:allow-other-keys)
              (let ((out (assoc-ref outputs "out"))
                    (glib-networking (assoc-ref inputs "glib-networking"))
                    (gtk (assoc-ref inputs "gtk+")))
                (wrap-program (string-append out "/bin/admincraft")
                  `("GIO_EXTRA_MODULES" ":" prefix
                    (,(string-append glib-networking "/lib/gio/modules")))
                  `("XDG_DATA_DIRS" ":" suffix
                    (,(string-append gtk "/share")))
                  ;; Common fix for WebKitGTK rendering on Wayland/NVIDIA.
                  `("WEBKIT_DISABLE_DMABUF_RENDERER" = ("1")))))))))
    (inputs (list glib glib-networking gtk+ webkitgtk))
    (native-inputs (list pkg-config rust `(,rust "cargo")))
    (synopsis "Branded, schema-driven admin client for Django REST Framework APIs")
    (description
     "admincraft is a Tauri 2 thin client that renders a complete
branded CRUD admin from the drf-spectacular OpenAPI schema of any Django
REST Framework backend, with a streaming OpenAI-compatible assistant.  Point
it at your API, log in with token credentials, and manage every model — no
per-model configuration.  The login screen accepts the API URL, so the same
binary works against any DRF deployment.")
    (home-page "https://github.com/khaalidrafi/admincraft")
    (license license:expat)))

;; `guix build -f guix.scm` evaluates this file; return the package.
admincraft
