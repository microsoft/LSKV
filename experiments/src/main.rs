use clap::Parser;
use std::path::PathBuf;
use tracing::info;
use tracing::metadata::LevelFilter;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;

mod stores;
mod ycsb;

#[derive(Debug, clap::Parser)]
struct Args {
    #[clap(long)]
    root_dir: PathBuf,

    #[clap(long)]
    results_dir: PathBuf,

    #[clap(long)]
    run: bool,

    #[clap(long)]
    analyse: bool,
}

#[tokio::main]
async fn main() {
    tracing_subscriber::registry()
        .with(tracing_subscriber::fmt::layer())
        .with(
            tracing_subscriber::EnvFilter::builder()
                .with_default_directive(LevelFilter::INFO.into())
                .from_env_lossy(),
        )
        .init();

    let args = Args::parse();
    info!(?args, "Parsed arguments");

    let mut experiment = ycsb::YcsbExperiment {
        root_dir: args.root_dir.clone(),
    };
    if args.run {
        exp::run(
            &mut experiment,
            &exp::RunConfig {
                results_dir: args.results_dir.clone(),
            },
        )
        .await
        .unwrap();
    }
    if args.analyse {
        exp::analyse(
            &mut experiment,
            &exp::AnalyseConfig {
                results_dir: args.results_dir,
            },
        )
        .await
        .unwrap();
    }
}
