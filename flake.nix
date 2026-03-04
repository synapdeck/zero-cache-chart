{
  description = "zero-cache Helm chart version manager";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = inputs@{ flake-parts, nixpkgs, pyproject-nix, uv2nix, pyproject-build-systems, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" "x86_64-darwin" ];

      perSystem = { pkgs, system, ... }:
        let
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

          venv = pythonSet.mkVirtualEnv "zero-cache-chart-env" workspace.deps.default;
          devVenv = pythonSet.mkVirtualEnv "zero-cache-chart-dev-env" workspace.deps.all;
        in
        {
          packages.default = venv;

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
