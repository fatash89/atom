#include <iostream>
#include <chrono>
#include <string>
#include <fstream>
#include <vector>

#include <bredis/Connection.hpp>
#include <bredis/Extract.hpp>
#include <bredis/MarkerHelpers.hpp>
#include <boost/asio.hpp>
#include <boost/algorithm/string.hpp>

template<typename socket, typename endpoint, typename buffer, typename iterator, typename policy> 
class bredis_client {

    public:
    bredis_client(boost::asio::io_context & ioserv, std::string ip_address, int port, std::string & img_str) : ioserv(ioserv),
                ep(boost::asio::ip::address::from_string(ip_address), boost::lexical_cast<std::uint16_t>(port)), sock(ioserv), bredis_con(std::move(sock)) {
        img = img_str;
        counter = 0;
    }

    ~bredis_client(){}

    void start(){
        sock.async_connect(ep, std::bind(&bredis_client::on_connect, this, std::placeholders::_1));
    }

    void on_connect(const boost::system::error_code& err){
        if(!err){
            std::cout<<"Connection to Redis was successful: " << err.message() <<std::endl;
            if(!sock.is_open()){
                std::cout<<"Socket closed... Connection timed out." <<std::endl;
            } else{
                do_async_xadd();
            }
        } else{
            std::cout<<"Connection was unsuccessful: "<<  err.message() << std::endl;
        }
    }

    void do_async_xadd(){
        std::cout<<"do_async_xadd"<<std::endl;
        bredis_con.async_write(xadd_tx_buff, bredis::single_command_t{ "XADD", "bredis", "*",  "nasa_pic", img}, std::bind(&bredis_client::on_async_xadd_write, this, std::placeholders::_1, std::placeholders::_2 ));
    }

    void on_async_xadd_write(const boost::system::error_code &err, std::size_t bytes_transferred){
        std::cout<<"on_async_xadd_write"<<std::endl;
        if(!err){
            // tx_buff must be consumed when it is no longer needed
            xadd_tx_buff.consume(bytes_transferred);
            bredis_con.async_read(xadd_rx_buff, std::bind(&bredis_client::on_xadd_read, this, std::placeholders::_1, std::placeholders::_2));
        } else{
            std::cout<<"XADD write was unsuccessful: "<<  err.message() << std::endl;
        }
    }

    void on_xadd_read(const boost::system::error_code &err, bredis::parse_result_mapper_t<iterator, policy> &&result_markers) {
        std::cout<<"on_xadd_read"<<std::endl;

        if(!err){                
            // consume the buffers, after finishing work with the markers
            xadd_rx_buff.consume(result_markers.consumed);

            if(counter < 100){
                std::cout<<"continuing..."<<std::endl;
                do_async_xadd();
            } else{
                std::cout<<"Closing socket."<<std::endl;
                sock.close();
            }
        } else{
            std::cout<<"XADD read was unsuccessful: "<<  err.message() << std::endl;
        }
    }

    //members
    boost::asio::io_context& ioserv;
    endpoint ep;
    std::shared_ptr<socket> sock;
    bredis::Connection<socket> bredis_con;
    int counter;
    buffer xadd_tx_buff;
    buffer xadd_rx_buff;
    std::string img; 
};


int main(){
    // log file setup here
    std::ofstream bredis_logfile;
    bredis_logfile.open("async_bredis.log", std::ios_base::app);
    bredis_logfile << "----- LOGGING AT: " + 
        std::to_string(std::chrono::duration_cast<std::chrono::milliseconds>
            (std::chrono::system_clock::now().time_since_epoch()).count()) + "-----\n";
    
    bredis_logfile << "xadd (ms), xadd read (ms), xadd extraction (ms), xrange (ms), xrange read (ms), xrange extraction (ms)\n";

    //for timing
    std::vector<std::string> xadd_times;
    std::vector<std::string> xadd_read_times;
    std::vector<std::string> xadd_extract_times;
    std::vector<std::string> xrange_times;
    std::vector<std::string> xrange_read_times;
    std::vector<std::string> xrange_extract_times;

    int iters = 100;

    //defining types here
    using socket_t = boost::asio::ip::tcp::socket;
    using endpoint_t = boost::asio::ip::tcp::endpoint;
    using next_layer_t = socket_t;

    using Buffer = boost::asio::streambuf;
    using Iterator = typename bredis::to_iterator<Buffer>::iterator_t;
    using Policy = bredis::parsing_policy::keep_result;
        
    boost::asio::io_context ioserv;

    /* unix socket here */
    //using socket_t = boost::asio::local::stream_protocol::socket;
    //using next_layer_t = socket_t;

    //boost::asio::local::stream_protocol::endpoint end_point("/shared/redis.sock");
    //socket_t sock(ioserv);
    //sock.connect("/shared/redis.sock");

    //read image in
    std::ifstream img_file("./clients/data/nasa1.jpg", std::ios::binary);
    std::string img_string = std::string((std::istreambuf_iterator<char>(img_file)), std::istreambuf_iterator<char>());

    //start write timer
    std::chrono::time_point<std::chrono::high_resolution_clock> start_w = std::chrono::high_resolution_clock::now();


    bredis_client<socket_t, endpoint_t, Buffer, Iterator, Policy> bredis_cli(ioserv, "172.19.0.2", 6379, img_string);

    bredis_cli.start();

    //end write timer
    std::chrono::time_point<std::chrono::high_resolution_clock> stop_w = std::chrono::high_resolution_clock::now();
    auto dur_w = std::chrono::duration_cast<std::chrono::milliseconds>(stop_w - start_w);


    ioserv.run();

}