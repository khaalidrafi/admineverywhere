{
  description = "admincraft — branded, schema-driven admin client (Tauri 2) for Django REST Framework APIs";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

    # Prebuilt web bundle (vite output). The repo ships only a README here;
    # pass the real bundle at build time:
    #   (cd app && npm ci && npm run build)
    #   nix build --override-input frontend-dist "$(nix store add-path app/dist)" .#admincraft
    frontend-dist = {
      url = "path:./frontend-dist";
      flake = false;
    };
  };

  outputs = { self, nixpkgs, frontend-dist }:
    let
      linuxSystems = [ "x86_64-linux" "aarch64-linux" ];
      forAllLinux = f: builtins.listToAttrs (map (system: {
        name = system;
        value = f nixpkgs.legacyPackages.${system};
      }) linuxSystems);
    in {
      # Built with rustPlatform.buildRustPackage + cargoLock as documented in
      # the nixpkgs manual ("Rust" chapter: vendoring dependencies directly
      # from a Cargo.lock file). No manual crate hashes.
      packages = forAllLinux (pkgs:
        let
          # Fail loudly (with instructions) if the frontend input is the stub.
          frontendDist =
            if builtins.pathExists (frontend-dist + "/index.html")
            then frontend-dist
            else builtins.throw ''
              frontend-dist contains no index.html.

              The repo deliberately ships no prebuilt web bundle. Build it first:

                  cd app && npm ci && npm run build

              then rebuild with:

                  nix build --override-input frontend-dist "$(nix store add-path app/dist)" .#admincraft
            '';
        in rec {
          admincraft = pkgs.rustPlatform.buildRustPackage {
            pname = "admincraft";
            version = "0.1.0";

            # Rust side only — the checkout provides Cargo.toml/lock, src/,
            # tauri.conf.json, icons/ and capabilities/. The web bundle comes
            # from the frontend-dist input, injected via TAURI_CONFIG (the
            # documented env override for Tauri builds; frontendDist accepts
            # an absolute path, so no source patching is needed).
            src = ./app/src-tauri;
            cargoLock.lockFile = ./app/src-tauri/Cargo.lock;

            env.TAURI_CONFIG = builtins.toJSON {
              build.frontendDist = "${frontendDist}";
            };

            nativeBuildInputs = with pkgs; [
              pkg-config
              wrapGAppsHook3
            ];
            buildInputs = with pkgs; [
              webkitgtk_4_1
              gtk3
              glib
              glib-networking
            ];

            gappsWrapperArgs = [
              "--set GIO_EXTRA_MODULES ${pkgs.glib-networking}/lib/gio/modules"
              "--set WEBKIT_DISABLE_DMABUF_RENDERER 1"
            ];

            doCheck = false; # no meaningful cargo tests in the Tauri shell

            meta = with pkgs.lib; {
              description = "Branded schema-driven admin client for Django REST Framework APIs";
              homepage = "https://github.com/khaalidrafi/admincraft";
              license = licenses.mit;
              mainProgram = "admincraft";
              platforms = platforms.linux;
            };
          };
          default = admincraft;
        });

      devShells = forAllLinux (pkgs: pkgs.mkShell {
        packages = with pkgs; [
          nodejs
          rustc
          cargo
          pkg-config
          webkitgtk_4_1
          gtk3
          glib-networking
        ];
      });
    };
}
