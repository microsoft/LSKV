use crate::ycsb::YcsbDispatcherGenerator;
use crate::ycsb::YcsbInputGenerator;
use loadbench::output_sink::StatsOutputSink;
use rand::rngs::StdRng;
use rand::SeedableRng;

pub mod args;
pub mod protos;
pub mod ycsb;

pub async fn run(args: args::Args) {
    match args.cmd {
        args::ArgVariants::Ycsb(ycsb_args) => run_ycsb(args.common_args, ycsb_args).await,
    }
}

pub async fn run_ycsb(args: args::CommonArgs, ycsb_args: crate::ycsb::Args) {
    let input_generator = YcsbInputGenerator {
        read_weight: ycsb_args.read_weight,
        scan_weight: ycsb_args.scan_weight,
        insert_weight: ycsb_args.insert_weight,
        update_weight: ycsb_args.update_weight,
        fields_per_record: ycsb_args.fields_per_record,
        field_value_length: ycsb_args.field_value_length,
        operation_rng: StdRng::from_entropy(),
        max_record_index: ycsb_args.max_record_index,
        max_scan_length: ycsb_args.max_scan_length,
        request_distribution: ycsb_args.request_distribution,
    };

    let dispatcher_generator = YcsbDispatcherGenerator::new(args.endpoint, &args.common_dir).await;

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
