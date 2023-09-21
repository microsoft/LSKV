pub mod etcd;
pub mod lskv;

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(tag = "store", rename_all = "lowercase")]
pub enum StoreConfig {
    Lskv(lskv::Config),
    Etcd(etcd::Config),
}
