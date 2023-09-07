fn main() -> Result<(), Box<dyn std::error::Error>> {
    tonic_build::configure().build_server(false).compile(
        &[
            "../proto/etcd.proto",
            "../proto/status.proto",
            "../proto/lskvserver.proto",
        ],
        &["../proto"],
    )?;
    Ok(())
}
