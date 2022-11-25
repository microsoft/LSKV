{
  description = "Confidential computing packages";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.flake-utils.url = "github:numtide/flake-utils";
  inputs.nix-filter.url = "github:numtide/nix-filter";

  outputs = {
    self,
    nixpkgs,
    flake-utils,
    nix-filter,
  }: let
    system = "x86_64-linux";
    pkgs = import nixpkgs {
      system = system;
      overlays = [nix-filter.overlays.default];
    };
    nix = import ./nix {
      inherit pkgs;
    };
    ci-checks-all = pkgs.symlinkJoin {
      name = "ci-checks-all";
      paths = with nix.ci-checks; [shellcheck prettier black pylint mypy cpplint nixfmt];
    };
    ci-checks-all-fix =
      pkgs.writeShellScriptBin
      "ci-checks-all"
      ''
        ${nix.ci-checks.prettier-fix}/bin/prettier
        ${nix.ci-checks.black-fix}/bin/black
        ${nix.ci-checks.nixfmt-fix}/bin/nixfmt
      '';
  in {
    packages.${system} =
      (flake-utils.lib.filterPackages system nix)
      // {
        inherit ci-checks-all ci-checks-all-fix;
      };

    overlays.${system}.default = final: prev: {
      ccf = self.packages.${system}.ccf;
    };

    checks.${system} =
      pkgs.lib.attrsets.filterAttrs
      (name: value: name != "override" && name != "overrideDerivation")
      nix.ci-checks
      // {
        inherit ci-checks-all ci-checks-all-fix;
        lskv-sandbox-virtual = self.packages.${system}.lskv-sandbox-virtual;
        lskv-sandbox-sgx = self.packages.${system}.lskv-sandbox-sgx;
      };

    lib = nix.lib;

    formatter.${system} = pkgs.alejandra;

    apps.${system} = {
      ccf-sandbox-virtual = flake-utils.lib.mkApp {
        drv = self.packages.${system}.ccf-sandbox-virtual;
        exePath = "/bin/sandbox.sh";
      };
      ccf-sandbox-sgx = flake-utils.lib.mkApp {
        drv = self.packages.${system}.ccf-sandbox-sgx;
        exePath = "/bin/sandbox.sh";
      };

      lskv-sandbox-virtual = flake-utils.lib.mkApp {
        drv = self.packages.${system}.lskv-sandbox-virtual;
        exePath = "/bin/lskv-sandbox.sh";
      };
      lskv-sandbox-sgx = flake-utils.lib.mkApp {
        drv = self.packages.${system}.lskv-sandbox-sgx;
        exePath = "/bin/lskv-sandbox.sh";
      };
    };

    devShells.${system}.default = pkgs.mkShell {
      packages = with pkgs; [
        rnix-lsp
      ];
    };
  };
}
