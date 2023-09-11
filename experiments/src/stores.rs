pub mod lskv;

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub enum StoreConfig {
    Lskv(lskv::Config),
}
