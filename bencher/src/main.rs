use crate::ycsb::YcsbDispatcherGenerator;
use crate::ycsb::YcsbInputGenerator;
use clap::Parser;
use loadbench::output_sink::StatsOutputSink;
use rand::rngs::StdRng;
use rand::SeedableRng;
use tracing::info;
use tracing::metadata::LevelFilter;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;

mod args;
mod ycsb;

pub mod protos {
    pub mod etcdserverpb {
        tonic::include_proto!("etcdserverpb");
    }
    pub mod ccf_protobuf {
        tonic::include_proto!("ccf.protobuf");
    }
    pub mod lskvserverpb {
        tonic::include_proto!("lskvserverpb");
    }
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

    let args = args::Args::parse();
    info!(?args, "Parsed arguments");
    match args.cmd {
        args::ArgVariants::Ycsb(ycsb_args) => {
            let input_generator = YcsbInputGenerator {
                read_weight: ycsb_args.read_weight,
                scan_weight: ycsb_args.scan_weight,
                insert_weight: ycsb_args.insert_weight,
                update_weight: ycsb_args.update_weight,
                read_all_fields: ycsb_args.read_all_fields,
                fields_per_record: ycsb_args.fields_per_record,
                field_value_length: ycsb_args.field_value_length,
                operation_rng: StdRng::from_entropy(),
                max_record_index: ycsb_args.max_record_index,
                request_distribution: ycsb_args.request_distribution,
            };

            let dispatcher_generator =
                YcsbDispatcherGenerator::new(args.endpoint, &args.common_dir).await;

            let mut output_sink = StatsOutputSink::default();

            loadbench::generate_load(
                ycsb_args.rate,
                ycsb_args.initial_clients,
                ycsb_args.total,
                ycsb_args.max_clients,
                input_generator,
                dispatcher_generator,
                &mut output_sink,
            )
            .await;

            output_sink.summary();
        }
    }
}
