use std::path::PathBuf;

#[derive(Debug, clap::Parser)]
pub struct Args {
    #[clap(subcommand)]
    pub cmd: ArgVariants,

    #[clap(flatten)]
    pub common_args: CommonArgs,
}

#[derive(Debug, clap::Args)]
pub struct CommonArgs {
    #[clap(long)]
    pub endpoint: String,

    #[clap(long)]
    pub common_dir: PathBuf,

    #[clap(long)]
    pub out_file: PathBuf,
}

#[derive(Debug, clap::Subcommand)]
pub enum ArgVariants {
    Ycsb(crate::ycsb::Args),
}
