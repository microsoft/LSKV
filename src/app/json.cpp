// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#include "json.h"

#include "ccf/crypto/base64.h"
#include "nlohmann/json.hpp"

#define CONTAINS_THEN_SET(ty, var) \
  if (j.contains(#var)) \
  { \
    ty v; \
    j.at(#var).get_to(v); \
    req.set_##var(v); \
  }

std::string to_base64(const std::string& d)
{
  std::vector<uint8_t> v(d.begin(), d.end());
  return crypto::b64_from_raw(v);
}

std::string from_base64(const std::string& b)
{
  auto d = crypto::raw_from_b64(b);
  return std::string(d.begin(), d.end());
}

namespace etcdserverpb
{
  using json = nlohmann::json;

  void from_json(const json& j, RangeRequest& req)
  {
    std::string key_b64;
    j.at("key").get_to(key_b64);
    req.set_key(from_base64(key_b64));

    if (j.contains("range_end"))
    {
      std::string range_end_b64;
      j.at("range_end").get_to(range_end_b64);
      req.set_range_end(from_base64(range_end_b64));
    }

    CONTAINS_THEN_SET(int64_t, limit);
    CONTAINS_THEN_SET(int64_t, revision);
    CONTAINS_THEN_SET(bool, serializable);
    CONTAINS_THEN_SET(bool, keys_only);
    CONTAINS_THEN_SET(bool, count_only);
    CONTAINS_THEN_SET(int64_t, min_mod_revision);
    CONTAINS_THEN_SET(int64_t, max_mod_revision);
    CONTAINS_THEN_SET(int64_t, min_create_revision);
    CONTAINS_THEN_SET(int64_t, max_create_revision);

    // sort_order
    // sort_target
  }

  void to_json(json& j, const KeyValue& kv)
  {
    j["key"] = to_base64(kv.key());
    j["create_revision"] = kv.create_revision();
    j["mod_revision"] = kv.mod_revision();
    j["version"] = kv.version();
    j["value"] = to_base64(kv.value());
    j["lease"] = kv.lease();
  }

  void to_json(json& j, const RangeResponse& res)
  {
    auto kvs = json::array();
    for (const auto& kv : res.kvs())
    {
      json jkv = json{};
      to_json(jkv, kv);
      kvs.push_back(jkv);
    }
    j["kvs"] = kvs;
    j["more"] = false;
    j["count"] = res.count();
  }

  void from_json(const json& j, PutRequest& req)
  {
    std::string key_b64;
    j.at("key").get_to(key_b64);
    req.set_key(from_base64(key_b64));

    std::string value_b64;
    j.at("value").get_to(value_b64);
    req.set_value(from_base64(value_b64));

    CONTAINS_THEN_SET(int64_t, lease);
    CONTAINS_THEN_SET(bool, prev_kv);
    CONTAINS_THEN_SET(bool, ignore_value);
    CONTAINS_THEN_SET(bool, ignore_lease);
  }

  void to_json(json& j, const PutResponse& res)
  {
    json jkv = json{};
    to_json(jkv, res.prev_kv());
    j["prev_kv"] = jkv;
  }

  void from_json(const json& j, DeleteRangeRequest& req)
  {
    std::string key_b64;
    j.at("key").get_to(key_b64);
    req.set_key(from_base64(key_b64));

    if (j.contains("range_end"))
    {
      std::string range_end_b64;
      j.at("range_end").get_to(range_end_b64);
      req.set_range_end(from_base64(range_end_b64));
    }

    CONTAINS_THEN_SET(bool, prev_kv);
  }

  void to_json(json& j, const DeleteRangeResponse& res)
  {
    j["deleted"] = res.deleted();

    auto kvs = json::array();
    for (const auto& kv : res.prev_kvs())
    {
      json jkv = json{};
      to_json(jkv, kv);
      kvs.push_back(jkv);
    }
    j["prev_kvs"] = kvs;
  }
};
