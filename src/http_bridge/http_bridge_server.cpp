/**
 * HTTP Bridge Server for OpenClaw <-> APP Communication
 * 实现APP期望的HTTP API端点，桥接ROS 2和Android APP
 */

#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/string.hpp>
#include <boost/beast/core.hpp>
#include <boost/beast/http.hpp>
#include <boost/beast/version.hpp>
#include <boost/asio/ip/tcp.hpp>
#include <boost/json.hpp>
#include <thread>
#include <memory>
#include <string>
#include <map>
#include <mutex>

namespace beast = boost::beast;
namespace http = beast::http;
namespace net = boost::asio;
using tcp = net::ip::tcp;
namespace json = boost::json;

// 全局状态管理
struct SystemState {
    std::string mode = "active";
    std::string main_mode = "ACTIVE";
    bool is_emergency_stop = false;
    bool is_safety_ok = true;
    int error_code = 0;
    std::string error_message = "";

    // 传感器数据
    float motor1_angle = 0.0f;
    float motor2_angle = 0.0f;
    float imu_angle_x = 0.0f;
    float emg_ch1 = 0.0f;
    int heart_rate = 0;
    float motor1_temp = 25.0f;
    float motor2_temp = 25.0f;

    std::mutex mtx;
};

class HttpBridgeNode : public rclcpp::Node {
public:
    HttpBridgeNode() : Node("http_bridge_node") {
        // 订阅CAN数据（从CAN节点接收传感器数据）
        can_rx_sub_ = this->create_subscription<std_msgs::msg::String>(
            "/can_rx", 10,
            std::bind(&HttpBridgeNode::canRxCallback, this, std::placeholders::_1));

        // 发布控制命令（发送到CAN节点）
        can_tx_pub_ = this->create_publisher<std_msgs::msg::String>("/can_tx", 10);

        RCLCPP_INFO(this->get_logger(), "HTTP Bridge Node initialized");
    }

    void publishCommand(const std::string& cmd_json) {
        auto msg = std_msgs::msg::String();
        msg.data = cmd_json;
        can_tx_pub_->publish(msg);
        RCLCPP_INFO(this->get_logger(), "Published command: %s", cmd_json.c_str());
    }

    SystemState& getState() { return state_; }

private:
    void canRxCallback(const std_msgs::msg::String::SharedPtr msg) {
        // 解析CAN数据并更新系统状态
        try {
            auto jv = json::parse(msg->data);
            std::lock_guard<std::mutex> lock(state_.mtx);

            if (jv.as_object().contains("motor1_angle"))
                state_.motor1_angle = jv.at("motor1_angle").as_double();
            if (jv.as_object().contains("motor2_angle"))
                state_.motor2_angle = jv.at("motor2_angle").as_double();
            if (jv.as_object().contains("imu_angle_x"))
                state_.imu_angle_x = jv.at("imu_angle_x").as_double();

        } catch (const std::exception& e) {
            RCLCPP_WARN(this->get_logger(), "Failed to parse CAN data: %s", e.what());
        }
    }

    rclcpp::Subscription<std_msgs::msg::String>::SharedPtr can_rx_sub_;
    rclcpp::Publisher<std_msgs::msg::String>::SharedPtr can_tx_pub_;
    SystemState state_;
};

// HTTP请求处理器
class HttpSession : public std::enable_shared_from_this<HttpSession> {
public:
    HttpSession(tcp::socket socket, std::shared_ptr<HttpBridgeNode> node)
        : socket_(std::move(socket)), node_(node) {}

    void run() {
        do_read();
    }

private:
    void do_read() {
        auto self = shared_from_this();
        http::async_read(socket_, buffer_, req_,
            [self](beast::error_code ec, std::size_t) {
                if (!ec) self->handle_request();
            });
    }

    void handle_request() {
        auto const bad_request = [](beast::string_view why) {
            http::response<http::string_body> res{http::status::bad_request, 11};
            res.set(http::field::content_type, "application/json");
            res.body() = json::serialize(json::object{{"error", why}});
            res.prepare_payload();
            return res;
        };

        auto const not_found = [](beast::string_view target) {
            http::response<http::string_body> res{http::status::not_found, 11};
            res.set(http::field::content_type, "application/json");
            res.body() = json::serialize(json::object{{"error", "Not found"}, {"path", target}});
            res.prepare_payload();
            return res;
        };

        auto const server_error = [](beast::string_view what) {
            http::response<http::string_body> res{http::status::internal_server_error, 11};
            res.set(http::field::content_type, "application/json");
            res.body() = json::serialize(json::object{{"error", what}});
            res.prepare_payload();
            return res;
        };

        http::response<http::string_body> res;
        res.version(req_.version());
        res.keep_alive(req_.keep_alive());
        res.set(http::field::content_type, "application/json");

        try {
            std::string target = std::string(req_.target());

            // GET /health - 健康检查
            if (req_.method() == http::verb::get && target == "/health") {
                res.result(http::status::ok);
                res.body() = json::serialize(json::object{{"status", "ok"}});
            }
            // GET /status - 获取系统状态和传感器数据
            else if (req_.method() == http::verb::get && target == "/status") {
                auto& state = node_->getState();
                std::lock_guard<std::mutex> lock(state.mtx);

                json::object status_obj{
                    {"timestamp", std::chrono::system_clock::now().time_since_epoch().count()},
                    {"mode", state.mode},
                    {"main_mode", state.main_mode},
                    {"is_emergency_stop", state.is_emergency_stop},
                    {"is_safety_ok", state.is_safety_ok},
                    {"error_code", state.error_code},
                    {"error_message", state.error_message},
                    {"motor1_angle", state.motor1_angle},
                    {"motor2_angle", state.motor2_angle},
                    {"imu_angle_x", state.imu_angle_x},
                    {"emg_ch1", state.emg_ch1},
                    {"heart_rate", state.heart_rate},
                    {"motor1_temp", state.motor1_temp},
                    {"motor2_temp", state.motor2_temp},
                    {"shoulder_angle", state.motor1_angle},
                    {"elbow_angle", state.motor2_angle},
                    {"lateral_position", state.imu_angle_x}
                };

                res.result(http::status::ok);
                res.body() = json::serialize(status_obj);
            }
            // POST /mode - 切换控制模式
            else if (req_.method() == http::verb::post && target == "/mode") {
                auto jv = json::parse(req_.body());
                std::string mode = json::value_to<std::string>(jv.at("mode"));

                {
                    std::lock_guard<std::mutex> lock(node_->getState().mtx);
                    node_->getState().mode = mode;
                }

                // 发送模式切换命令到CAN
                json::object cmd{{"type", "mode"}, {"mode", mode}};
                node_->publishCommand(json::serialize(cmd));

                res.result(http::status::ok);
                res.body() = json::serialize(json::object{{"success", true}, {"mode", mode}});
            }
            // POST /control - 发送控制指令
            else if (req_.method() == http::verb::post && target == "/control") {
                auto jv = json::parse(req_.body());
                json::object cmd{{"type", "control"}};

                if (jv.as_object().contains("shoulder_angle"))
                    cmd["shoulder_angle"] = jv.at("shoulder_angle").as_double();
                if (jv.as_object().contains("elbow_angle"))
                    cmd["elbow_angle"] = jv.at("elbow_angle").as_double();
                if (jv.as_object().contains("lateral_pos"))
                    cmd["lateral_pos"] = jv.at("lateral_pos").as_double();

                node_->publishCommand(json::serialize(cmd));

                res.result(http::status::ok);
                res.body() = json::serialize(json::object{{"success", true}});
            }
            // POST /memory/execute - 执行记忆动作
            else if (req_.method() == http::verb::post && target == "/memory/execute") {
                auto jv = json::parse(req_.body());
                std::string action_id = json::value_to<std::string>(jv.at("action_id"));

                json::object cmd{{"type", "memory"}, {"action_id", action_id}};
                node_->publishCommand(json::serialize(cmd));

                res.result(http::status::ok);
                res.body() = json::serialize(json::object{{"success", true}});
            }
            // POST /memory/stop - 停止记忆动作
            else if (req_.method() == http::verb::post && target == "/memory/stop") {
                json::object cmd{{"type", "stop_memory"}};
                node_->publishCommand(json::serialize(cmd));

                res.result(http::status::ok);
                res.body() = json::serialize(json::object{{"success", true}});
            }
            // POST /api/command - OpenClaw工具调用
            else if (req_.method() == http::verb::post && target == "/api/command") {
                auto jv = json::parse(req_.body());
                std::string tool = json::value_to<std::string>(jv.at("tool"));
                auto params = jv.at("parameters").as_object();

                json::object cmd{{"type", "tool"}, {"tool", tool}, {"parameters", params}};
                node_->publishCommand(json::serialize(cmd));

                res.result(http::status::ok);
                res.body() = json::serialize(json::object{
                    {"success", true},
                    {"result", "Command sent to OpenClaw"}
                });
            }
            else {
                res = not_found(req_.target());
            }

        } catch (const std::exception& e) {
            res = server_error(e.what());
        }

        res.prepare_payload();
        write_response(std::move(res));
    }

    void write_response(http::response<http::string_body>&& res) {
        auto self = shared_from_this();
        res_ = std::make_shared<http::response<http::string_body>>(std::move(res));

        http::async_write(socket_, *res_,
            [self](beast::error_code ec, std::size_t) {
                self->socket_.shutdown(tcp::socket::shutdown_send, ec);
            });
    }

    tcp::socket socket_;
    beast::flat_buffer buffer_;
    http::request<http::string_body> req_;
    std::shared_ptr<http::response<http::string_body>> res_;
    std::shared_ptr<HttpBridgeNode> node_;
};

// HTTP服务器监听器
class HttpListener : public std::enable_shared_from_this<HttpListener> {
public:
    HttpListener(net::io_context& ioc, tcp::endpoint endpoint,
                 std::shared_ptr<HttpBridgeNode> node)
        : ioc_(ioc), acceptor_(ioc), node_(node) {
        beast::error_code ec;

        acceptor_.open(endpoint.protocol(), ec);
        if (ec) throw beast::system_error{ec};

        acceptor_.set_option(net::socket_base::reuse_address(true), ec);
        if (ec) throw beast::system_error{ec};

        acceptor_.bind(endpoint, ec);
        if (ec) throw beast::system_error{ec};

        acceptor_.listen(net::socket_base::max_listen_connections, ec);
        if (ec) throw beast::system_error{ec};
    }

    void run() {
        do_accept();
    }

private:
    void do_accept() {
        acceptor_.async_accept(
            net::make_strand(ioc_),
            [self = shared_from_this()](beast::error_code ec, tcp::socket socket) {
                if (!ec) {
                    std::make_shared<HttpSession>(std::move(socket), self->node_)->run();
                }
                self->do_accept();
            });
    }

    net::io_context& ioc_;
    tcp::acceptor acceptor_;
    std::shared_ptr<HttpBridgeNode> node_;
};

int main(int argc, char** argv) {
    rclcpp::init(argc, argv);

    // 创建ROS节点
    auto node = std::make_shared<HttpBridgeNode>();

    // HTTP服务器配置
    auto const address = net::ip::make_address("0.0.0.0");
    auto const port = static_cast<unsigned short>(8081);

    // 创建IO上下文
    net::io_context ioc{1};

    // 创建并启动HTTP监听器
    std::make_shared<HttpListener>(ioc, tcp::endpoint{address, port}, node)->run();

    RCLCPP_INFO(node->get_logger(), "HTTP Bridge Server started on port %d", port);

    // 在单独线程中运行HTTP服务器
    std::thread http_thread([&ioc]() {
        ioc.run();
    });

    // 运行ROS节点
    rclcpp::spin(node);

    // 清理
    ioc.stop();
    http_thread.join();
    rclcpp::shutdown();

    return 0;
}
