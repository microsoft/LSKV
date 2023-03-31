# Nix configuration for building and running LSKV

This configuration includes dependencies such as python packages and C/C++ projects, primarily for CCF and its dependencies.

## Getting nix

If you don't have nix installed then follow the [official steps](https://nixos.org/download.html).

You'll also need to [enable flakes](https://nixos.wiki/wiki/Flakes#Enable_flakes).

## Listing outputs

```sh
nix flake show
```

## Building LSKV

To build lskv in virtual mode run the following from the root of the repo:

```sh
nix build .#lskv-virtual
```

Replace `virtual` for `sgx` to build that platform.

## Running LSKV

LSKV comes packaged with a sandbox based on the CCF one that uses the nix-built library directly.
To build and run it:

```sh
nix run .#lskv-sandbox-virtual -- --http2
```

Again, replace `virtual` for `sgx` to build that platform.

**Note**: Whilst SGX targets can be built on non-sgx hardware, running them will require the requisite hardware.
