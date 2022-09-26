#pragma once

#include "ccf/json_handler.h"
#include "etcd.pb.h"

namespace app::json
{
  class RangeRequest
  {
  public:
    std::string key;
    std::string range_end;
    etcdserverpb::RangeRequest to_grpc() const;
  };
  DECLARE_JSON_TYPE(RangeRequest);
  DECLARE_JSON_REQUIRED_FIELDS(RangeRequest, key);
}; // namespace app::json

namespace etcdserverpb
{

  using json = nlohmann::json;
  // Range
  void from_json(const json& j, RangeRequest& req);
  void to_json(json& j, const RangeResponse& res);
  // Put
  void from_json(const json& j, PutRequest& req);
  void to_json(json& j, const PutResponse& res);
};