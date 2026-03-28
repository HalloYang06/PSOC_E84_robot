#include <iostream>
#include <string>
#include <thread>
#include <chrono>
#include <vector>
#include <iomanip>
#include <opencv2/opencv.hpp>
#include <boost/beast/core.hpp>
#include <boost/beast/websocket.hpp>
#include <boost/asio/connect.hpp>
#include <boost/asio/ip/tcp.hpp>
#include <nlohmann/json.hpp>
#include <boost/beast/core/detail/base64.hpp>

namespace beast = boost::beast;
namespace http = beast::http;
namespace websocket = beast::websocket;
namespace net = boost::asio;
using tcp = boost::asio::ip::tcp;
using json = nlohmann::json;

class CameraWebSocketClient {
private:
    net::io_context ioc_;
    tcp::resolver resolver_;
    websocket::stream<tcp::socket> ws_;
    cv::VideoCapture camera_;
    std::string server_host_;
    std::string server_port_;
    bool connected_;
    int frame_rate_;

    // 自动检测可用的摄像头
    int findAvailableCamera() {
        std::cout << "Searching for available cameras..." << std::endl;

        // 尝试常见的摄像头设备号
        std::vector<int> camera_ids = {0, 1, 2, 45, 46};  // 45是你的USB摄像头

        for (int id : camera_ids) {
            cv::VideoCapture test_cam(id, cv::CAP_V4L2);
            if (test_cam.isOpened()) {
                // 设置 MJPEG 格式
                test_cam.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('M', 'J', 'P', 'G'));
                test_cam.set(cv::CAP_PROP_FRAME_WIDTH, 640);
                test_cam.set(cv::CAP_PROP_FRAME_HEIGHT, 480);

                // 等待摄像头初始化
                std::this_thread::sleep_for(std::chrono::milliseconds(300));

                // 尝试读取一帧来确认摄像头真的可用
                cv::Mat frame;
                if (test_cam.read(frame) && !frame.empty()) {
                    std::cout << "Found working camera at /dev/video" << id << std::endl;
                    test_cam.release();
                    return id;
                }
                test_cam.release();
            }
        }

        return -1;
    }

public:
    CameraWebSocketClient(const std::string& host, const std::string& port, int camera_id = -1, int fps = 10)
        : resolver_(ioc_)
        , ws_(ioc_)
        , server_host_(host)
        , server_port_(port)
        , connected_(false)
        , frame_rate_(fps)
    {
        // 如果没有指定摄像头ID，自动检测
        if (camera_id == -1) {
            camera_id = findAvailableCamera();
            if (camera_id == -1) {
                throw std::runtime_error("No available camera found");
            }
        }

        // 打开摄像头 - 强制使用 V4L2 后端并设置 MJPEG 格式
        std::cout << "Opening camera /dev/video" << camera_id << "..." << std::endl;
        camera_.open(camera_id, cv::CAP_V4L2);
        if (!camera_.isOpened()) {
            throw std::runtime_error("Failed to open camera /dev/video" + std::to_string(camera_id));
        }

        // 设置摄像头参数 - 先设置格式再设置分辨率
        camera_.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('M', 'J', 'P', 'G'));
        camera_.set(cv::CAP_PROP_FRAME_WIDTH, 640);
        camera_.set(cv::CAP_PROP_FRAME_HEIGHT, 480);
        camera_.set(cv::CAP_PROP_FPS, fps);

        // 等待摄像头稳定
        std::this_thread::sleep_for(std::chrono::milliseconds(500));

        // 显示实际的摄像头参数
        int actual_width = camera_.get(cv::CAP_PROP_FRAME_WIDTH);
        int actual_height = camera_.get(cv::CAP_PROP_FRAME_HEIGHT);
        double actual_fps = camera_.get(cv::CAP_PROP_FPS);

        std::cout << "Camera opened successfully" << std::endl;
        std::cout << "Resolution: " << actual_width << "x" << actual_height << std::endl;
        std::cout << "FPS: " << actual_fps << std::endl;
    }

    ~CameraWebSocketClient() {
        if (camera_.isOpened()) {
            camera_.release();
        }
        if (connected_) {
            disconnect();
        }
    }

    void connect() {
        try {
            // 解析服务器地址
            auto const results = resolver_.resolve(server_host_, server_port_);

            // 连接到服务器
            auto ep = net::connect(ws_.next_layer(), results);

            // 设置WebSocket握手
            ws_.handshake(server_host_ + ":" + server_port_, "/");

            connected_ = true;
            std::cout << "Connected to WebSocket server: " << server_host_ << ":" << server_port_ << std::endl;

            // 注册为ROS客户端
            json register_msg = {
                {"type", "register"},
                {"role", "ros"}
            };

            ws_.write(net::buffer(register_msg.dump()));

            // 读取注册响应
            beast::flat_buffer buffer;
            ws_.read(buffer);
            std::string response = beast::buffers_to_string(buffer.data());
            std::cout << "Registration response: " << response << std::endl;

        } catch (std::exception const& e) {
            std::cerr << "Connection error: " << e.what() << std::endl;
            connected_ = false;
            throw;
        }
    }

    void disconnect() {
        if (connected_) {
            try {
                ws_.close(websocket::close_code::normal);
                connected_ = false;
                std::cout << "Disconnected from server" << std::endl;
            } catch (std::exception const& e) {
                std::cerr << "Disconnect error: " << e.what() << std::endl;
            }
        }
    }

    std::string encodeImageToBase64(const cv::Mat& image) {
        // 将图像编码为JPEG
        std::vector<uchar> buffer;
        std::vector<int> params = {cv::IMWRITE_JPEG_QUALITY, 80};
        cv::imencode(".jpg", image, buffer, params);

        // 转换为base64
        std::string encoded;
        encoded.resize(beast::detail::base64::encoded_size(buffer.size()));
        encoded.resize(beast::detail::base64::encode(&encoded[0], buffer.data(), buffer.size()));

        return "data:image/jpeg;base64," + encoded;
    }

    void sendImage(const cv::Mat& image) {
        if (!connected_) {
            std::cerr << "Not connected to server" << std::endl;
            return;
        }

        try {
            // 直接编码图像为base64（不翻转）
            std::string base64_image = encodeImageToBase64(image);

            // 构建JSON消息
            json message = {
                {"type", "ros_data"},
                {"dataType", "image"},
                {"payload", base64_image}
            };

            // 发送消息
            ws_.write(net::buffer(message.dump()));

            // 不再每次都打印，由startStreaming统一显示帧率

        } catch (std::exception const& e) {
            std::cerr << "\nError sending image: " << e.what() << std::endl;
            connected_ = false;
        }
    }

    void startStreaming() {
        if (!connected_) {
            std::cerr << "Not connected to server" << std::endl;
            return;
        }

        std::cout << "Starting camera streaming at " << frame_rate_ << " FPS..." << std::endl;
        std::cout << "Press Ctrl+C to stop" << std::endl;

        cv::Mat frame;
        auto frame_duration = std::chrono::milliseconds(1000 / frame_rate_);

        // 帧率统计变量
        int frame_count = 0;
        auto fps_start_time = std::chrono::steady_clock::now();
        double actual_fps = 0.0;

        while (connected_) {
            auto start_time = std::chrono::steady_clock::now();

            // 捕获帧
            if (!camera_.read(frame)) {
                std::cerr << "Failed to capture frame" << std::endl;
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
                continue;
            }

            // 发送图像
            sendImage(frame);

            // 更新帧计数
            frame_count++;

            // 每秒计算一次实际帧率
            auto fps_elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - fps_start_time);

            if (fps_elapsed.count() >= 1000) {
                actual_fps = frame_count * 1000.0 / fps_elapsed.count();

                // 清除当前行并显示帧率
                std::cout << "\r[FPS: " << std::fixed << std::setprecision(1) << actual_fps
                          << " | Frames: " << frame_count
                          << " | Size: " << frame.cols << "x" << frame.rows << "]" << std::flush;

                // 重置计数器
                frame_count = 0;
                fps_start_time = std::chrono::steady_clock::now();
            }

            // 控制帧率
            auto end_time = std::chrono::steady_clock::now();
            auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(end_time - start_time);

            if (elapsed < frame_duration) {
                std::this_thread::sleep_for(frame_duration - elapsed);
            }
        }

        std::cout << std::endl; // 结束时换行
    }

    bool isConnected() const {
        return connected_;
    }
};

int main(int argc, char* argv[]) {
    try {
        // 默认参数
        std::string server_host = "10.100.191.235";
        std::string server_port = "8080";
        int camera_id = -1;  // -1 表示自动检测
        int fps = 10;

        // 解析命令行参数
        if (argc > 1) server_host = argv[1];
        if (argc > 2) server_port = argv[2];
        if (argc > 3) camera_id = std::stoi(argv[3]);
        if (argc > 4) fps = std::stoi(argv[4]);

        std::cout << "Camera WebSocket Client" << std::endl;
        std::cout << "Server: " << server_host << ":" << server_port << std::endl;
        if (camera_id == -1) {
            std::cout << "Camera ID: Auto-detect" << std::endl;
        } else {
            std::cout << "Camera ID: " << camera_id << std::endl;
        }
        std::cout << "Target FPS: " << fps << std::endl;
        std::cout << "------------------------" << std::endl;

        // 创建客户端
        CameraWebSocketClient client(server_host, server_port, camera_id, fps);

        // 连接到服务器
        client.connect();

        // 开始流式传输
        client.startStreaming();

    } catch (std::exception const& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return EXIT_FAILURE;
    }

    return EXIT_SUCCESS;
}
