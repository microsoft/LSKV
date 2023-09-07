use std::path::PathBuf;

#[derive(Debug, clap::Parser)]
pub struct Args {
    #[clap(subcommand)]
    pub cmd: ArgVariants,

    #[clap(long)]
    pub endpoint: String,

    #[clap(long)]
    pub common_dir: PathBuf,
}

#[derive(Debug, clap::Subcommand)]
pub enum ArgVariants {
    Ycsb(crate::ycsb::Args),
}
