{
  description = "zero-cache Helm chart version manager";

  inputs = {
    nixpkgs.url = "https://flakehub.com/f/NixOS/nixpkgs/0.1";
    flake-parts.url = "https://flakehub.com/f/hercules-ci/flake-parts/0.1";
    pyproject-nix = {
      url = "https://flakehub.com/f/pyproject-nix/pyproject.nix/0.1";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "https://flakehub.com/f/pyproject-nix/uv2nix/0.1";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-build-systems = {
      url = "https://flakehub.com/f/pyproject-nix/build-system-pkgs/0.1";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = inputs @ {
    flake-parts,
    nixpkgs,
    pyproject-nix,
    uv2nix,
    pyproject-build-systems,
    ...
  }:
    flake-parts.lib.mkFlake {inherit inputs;} {
      systems = ["x86_64-linux" "aarch64-linux" "aarch64-darwin" "x86_64-darwin"];

      flake.chartMetadata = import ./chart.nix;

      flake.chart = let
        helmFiles = builtins.path {
          path = ./.;
          name = "zero-cache-chart-src";
          filter = path: type: let
            base = builtins.baseNameOf path;
            relPath = builtins.substring (builtins.stringLength (toString ./.) + 1) (-1) (toString path);
          in
            builtins.elem base ["Chart.yaml" "values.yaml" "Chart.lock" ".helmignore"]
            || nixpkgs.lib.hasPrefix "templates" relPath;
        };
      in
        helmFiles;

      perSystem = {
        pkgs,
        system,
        ...
      }: let
        workspace = uv2nix.lib.workspace.loadWorkspace {
          workspaceRoot = ./.;
        };

        overlay = workspace.mkPyprojectOverlay {
          sourcePreference = "wheel";
        };

        pythonSet =
          (pkgs.callPackage pyproject-nix.build.packages {
            python = pkgs.python3;
          }).overrideScope (
            nixpkgs.lib.composeManyExtensions [
              pyproject-build-systems.overlays.default
              overlay
            ]
          );

        inherit (pkgs.callPackages pyproject-nix.build.util {}) mkApplication;

        venv = pythonSet.mkVirtualEnv "zero-cache-chart-env" workspace.deps.default;
        devVenv = pythonSet.mkVirtualEnv "zero-cache-chart-dev-env" workspace.deps.all;

        unwrapped = mkApplication {
          venv = venv;
          package = pythonSet.zero-cache-chart;
        };
      in {
        packages.default = pkgs.symlinkJoin {
          name = "zero-cache-chart";
          paths = [unwrapped];
          nativeBuildInputs = [pkgs.makeWrapper];
          postBuild = ''
            wrapProgram $out/bin/zero-cache-chart \
              --prefix PATH : ${pkgs.lib.makeBinPath [pkgs.kubernetes-helm pkgs.oras]}
          '';
        };

        devShells.default = pkgs.mkShell {
          packages = [
            devVenv
            pkgs.kubernetes-helm
            pkgs.kubeconform
            pkgs.helm-docs
            pkgs.oras
            pkgs.uv
          ];

          env = {
            UV_NO_SYNC = "1";
            UV_PYTHON = pythonSet.python.interpreter;
            UV_PYTHON_DOWNLOADS = "never";
          };

          shellHook = ''
            unset PYTHONPATH
          '';
        };
      };
    };
}
