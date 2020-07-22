#include <iostream>
#include <chrono>
#include <string>
#include <fstream>
#include <vector>
#include <csignal>

#include <bredis/Connection.hpp>
#include <bredis/Extract.hpp>
#include <bredis/MarkerHelpers.hpp>
#include <boost/asio.hpp>
#include <boost/algorithm/string.hpp>

template<typename socket, typename endpoint, typename buffer, typename iterator, typename policy> 
class bredis_client {

    public:
    //constructor for tcp socket connection
    bredis_client(boost::asio::io_context & iocon, std::string ip_address, int port, std::string & img_str) : 
        iocon(iocon),
        ep(boost::asio::ip::address::from_string(ip_address), 
        boost::lexical_cast<std::uint16_t>(port)), 
        sock(std::make_shared<socket>(iocon)), 
        bredis_con(nullptr) {
        img = img_str;
        counter = 0;
    }
    
    //constructor for unix socket connection
    bredis_client(boost::asio::io_context & iocon, std::string sock_addr, std::string & img_str) : 
            iocon(iocon),
            ep(sock_addr), 
            sock(std::make_shared<socket>(iocon)), 
            bredis_con(nullptr) {
        img = img_str;
        counter = 0;
    }

    ~bredis_client(){
        std::cout<<"Destruction."<<std::endl;
        if(sock->is_open()){
            sock->close();
        }
    }
    
    void stop(){
        std::cout<< "Closing Socket" <<std::endl;
        sock->close();
    }

    void start(){
        sock->async_connect(ep, std::bind(&bredis_client::on_connect, this, std::placeholders::_1));
    }

    void on_connect(const boost::system::error_code& err){
        if(err){
            std::cout<<"Connection was unsuccessful: "<<  err.message() << std::endl;   
            stop();        
        } else{
            std::cout<<"Connection to Redis was successful: " << err.message() <<std::endl;
            if(!sock->is_open()){
                std::cout<<"Socket closed... Connection timed out." <<std::endl;
            } else{
                bredis_con = std::make_shared<bredis::Connection<socket>>(std::move(*sock));
                do_async_xadd();
            }
        }
    }

    void do_async_xadd(){
        std::cout<<"do_async_xadd"<<std::endl;
        bredis_con->async_write(xadd_tx_buff, bredis::single_command_t{ "XADD", "bredis", "*",  "nasa_pic", "picture"}, std::bind(&bredis_client::on_async_xadd_write, this, std::placeholders::_1, std::placeholders::_2 ));
    }

    void on_async_xadd_write(const boost::system::error_code &err, std::size_t bytes_transferred){
        std::cout<<"on_async_xadd_write"<<std::endl;
        if(err){
            std::cout<<"XADD write was unsuccessful: "<<  err.message() << std::endl;
            stop();         
        } else{
            // tx_buff must be consumed when it is no longer needed
            xadd_tx_buff.consume(bytes_transferred);
            bredis_con->async_read(xadd_rx_buff, std::bind(&bredis_client::on_xadd_read, this, std::placeholders::_1, std::placeholders::_2));
        }
    }

    void on_xadd_read(const boost::system::error_code &err, bredis::parse_result_mapper_t<iterator, policy> &&result_markers) {
        std::cout<<"on_xadd_read"<<std::endl;

        if(err){                
            std::cout<<"XADD read was unsuccessful: "<<  err.message() << std::endl;
            stop();
        } else{
            // consume the buffers, after finishing work with the markers
            xadd_rx_buff.consume(result_markers.consumed);

            if(counter < 100){
                std::cout<<"continuing..."<<std::endl;
                do_async_xadd();
            } else{
                stop();
            }        
        }
    }

    //members
    boost::asio::io_context& iocon;
    endpoint ep;
    std::shared_ptr<socket> sock;
    std::shared_ptr<bredis::Connection<socket>> bredis_con;
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

    /* tcp socket types */
    /* using socket_t = boost::asio::ip::tcp::socket;
    using endpoint_t = boost::asio::ip::tcp::endpoint;
    using next_layer_t = socket_t; */
    
    /* unix socket types */
    using socket_t = boost::asio::local::stream_protocol::socket;
    using next_layer_t = socket_t;
    using endpoint_t = boost::asio::local::stream_protocol::endpoint;

    using Buffer = boost::asio::streambuf;
    using Iterator = typename bredis::to_iterator<Buffer>::iterator_t;
    using Policy = bredis::parsing_policy::keep_result;
        
    boost::asio::io_context iocon;

    //read image in
    std::ifstream img_file("./clients/data/nasa1.jpg", std::ios::binary);
    std::string img_string = std::string((std::istreambuf_iterator<char>(img_file)), std::istreambuf_iterator<char>());

    //start write timer
    std::chrono::time_point<std::chrono::high_resolution_clock> start_w = std::chrono::high_resolution_clock::now();


    //bredis_client<socket_t, endpoint_t, Buffer, Iterator, Policy> bredis_cli(iocon, "172.19.0.2", 6379, img_string);
    bredis_client<socket_t, endpoint_t, Buffer, Iterator, Policy> bredis_cli(iocon, "/shared/redis.sock", img_string);

    bredis_cli.start();

    //end write timer
    std::chrono::time_point<std::chrono::high_resolution_clock> stop_w = std::chrono::high_resolution_clock::now();
    auto dur_w = std::chrono::duration_cast<std::chrono::milliseconds>(stop_w - start_w);

    //signal handling
/*     boost::asio::signal_set signals(iocon, SIGINT);
    signals.async_wait([&](const boost::system::error_code& error, int signal_number) {
                                bredis_cli.stop();
                                return signal_number;
                            }); */

    iocon.run();

    return 0;

}