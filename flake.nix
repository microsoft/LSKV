{
  description = "Confidential computing packages";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.flake-utils.url = "github:numtide/flake-utils";
  inputs.nix-filter.url = "github:numtide/nix-filter";

  outputs = { self, nixpkgs, flake-utils, nix-filter }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs {
        system = system;
        overlays = [nix-filter.overlays.default];
      };
      nix= import ./nix {
        inherit pkgs;
      };
    in
    {
      packages.${system} = flake-utils.lib.filterPackages system nix;

      checks.${system} = pkgs.lib.attrsets.filterAttrs
        (name: value: name != "override" && name != "overrideDerivation")
        nix.ci-checks;

      apps.${system} = {
        ccf-sandbox = flake-utils.lib.mkApp {
          drv = self.packages.${system}.ccf-sandbox;
          exePath = "/bin/sandbox.sh";
        };

        lskv-sandbox = flake-utils.lib.mkApp {
          drv = self.packages.${system}.lskv-sandbox;
          exePath = "/bin/lskv-sandbox.sh";
        };
      };

      devShells.${system}.default = pkgs.mkShell {
        packages = with pkgs; [
          rnix-lsp
          nixpkgs-fmt
        ];
      };
    };
}
