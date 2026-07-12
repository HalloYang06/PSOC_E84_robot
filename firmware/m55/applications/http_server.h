#ifndef __HTTP_SERVER_H__
#define __HTTP_SERVER_H__

#include <rtthread.h>

#define HTTP_SERVER_PORT 8081

rt_err_t http_server_init(void);

#endif
