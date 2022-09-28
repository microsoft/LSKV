// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#pragma once

namespace app::exceptions
{
  struct BadRequest : public std::exception
  {
    ccf::ErrorDetails error;

    BadRequest(std::string&& msg) :
      error{HTTP_STATUS_BAD_REQUEST, ccf::errors::InvalidInput, msg}
    {}

    const char* what() const throw() override
    {
      return error.msg.c_str();
    }
  };

  struct WrongMediaType : public std::exception
  {
    ccf::ErrorDetails error;

    WrongMediaType(std::string&& msg) :
      error{
        HTTP_STATUS_UNSUPPORTED_MEDIA_TYPE,
        ccf::errors::UnsupportedContentType,
        msg}
    {}

    const char* what() const throw() override
    {
      return error.msg.c_str();
    }
  };

}
