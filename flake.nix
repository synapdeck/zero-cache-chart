{
  description = "zero-cache Helm chart version manager";

  inputs = {
    nixpkgs.url = "https://flakehub.com/f/NixOS/nixpkgs/0.1";
    flake-parts.url = "https://flakehub.com/f/hercules-ci/flake-parts/0.1";
  };

  outputs = inputs @ {
    flake-parts,
    nixpkgs,
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

      perSystem = {pkgs, ...}: let
        python = pkgs.python3;

        zero-cache-chart = python.pkgs.buildPythonApplication {
          pname = "zero-cache-chart";
          version = "0.0.0";
          pyproject = true;

          src = ./.;

          build-system = [python.pkgs.hatchling];

          dependencies = with python.pkgs; [
            click
            pyyaml
            requests
            semver
          ];

          nativeCheckInputs =
            [pkgs.git]
            ++ (with python.pkgs; [
              pytestCheckHook
              pytest-mock
              responses
            ]);

          makeWrapperArgs = [
            "--prefix PATH : ${pkgs.lib.makeBinPath [pkgs.kubernetes-helm pkgs.oras]}"
          ];
        };
      in {
        packages.default = zero-cache-chart;

        devShells.default = pkgs.mkShell {
          packages = [
            (python.withPackages (ps:
              with ps; [
                click
                pyyaml
                requests
                semver
                pytest
                pytest-mock
                responses
              ]))
            pkgs.kubernetes-helm
            pkgs.kubeconform
            pkgs.helm-docs
            pkgs.oras
          ];
        };
      };
    };
}
