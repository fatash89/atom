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

template<class socket, class endpoint, class buffer, class iterator, class policy> 
class bredis_client {
    bredis_client(boost::asio::io_service & ioserv, std::string ip_address, int port) : counter(0){
        //create socket & connect to endpoint
        auto ip_address = boost::asio::ip::address::from_string("172.20.0.2");
        auto port = boost::lexical_cast<std::uint16_t>(6379);
        endpoint ep(ip_address, port);
        socket sock(ioserv, end_point.protocol());
        sock.connect(end_point);
        bredis::Connection<socket> bredis_con(std::move(sock));

        std::cout<<"Redis client is connected!"<<std::endl;
    }

    ~bredis_client(){};

    void do_async_xadd(){
        bredis_con.async_write(xadd_tx_buff, bredis::single_command_t{ "XADD", "bredis", "*", key, img_binary }, do_async_read);
    }

    void do_async_xadd_read(){
        // tx_buff must be consumed when it is no longer needed
        xadd_tx_buff.consume(bytes_transferred);
        bredis_con.async_read(xadd_rx_buff, on_xadd_read);
    }

    void on_xadd_read(const boost::system::error_code &ec, std::size_t bytes_transferred) {
        auto extract = boost::apply_visitor(bredis::extractor<Iterator>(), result_markers.result);
        try{
            auto &reply_str = boost::get<bredis::extracts::string_t>(extract);
        }catch(boost::bad_get &err){
            std::cout<<"XADD ERROR @ iter:" << i << ": "<< err.what()<< std::endl;
            //auto &reply_str = boost::get<bredis::extracts::error_t>(extract); //getting bad boost lexical ast here?
            //std::cout<<reply_str.str<<std::endl;
            exit(EXIT_FAILURE);
        }
                
        // consume the buffers, after finishing work with the markers
        xadd_rx_buff.consume(result_markers.consumed);

        if(count < 100){
            do_async_xadd();
        }
    }

    //members
    socket sock;
    endpoint ep;
    bredis::Connection<next_layer_t> bredis_con;
    int counter;
    Buffer xadd_tx_buff;
    Buffer xadd_rx_buff;
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
        
    boost::asio::io_service ioserv;

    /* unix socket here */
    //using socket_t = boost::asio::local::stream_protocol::socket;
    //using next_layer_t = socket_t;

    //boost::asio::local::stream_protocol::endpoint end_point("/shared/redis.sock");
    //socket_t sock(ioserv);
    //sock.connect("/shared/redis.sock");
    

    /* //create socket & connect to endpoint
    auto ip_address = boost::asio::ip::address::from_string("172.20.0.2");
    auto port = boost::lexical_cast<std::uint16_t>(6379);
    boost::asio::ip::tcp::endpoint end_point(ip_address, port);
    socket_t socket(ioserv, end_point.protocol());
    socket.connect(end_point); */


    //wrap socket in bredis connection
    //bredis::Connection<next_layer_t> bredis_con(std::move(socket));

    //create buffers
    //Buffer xadd_tx_buff, xadd_rx_buff;
    //Buffer xrange_tx_buff, xrange_rx_buff;

    //read image in
    std::ifstream img_file("./clients/data/nasa1.jpg", std::ios::binary);
    std::string img_binary = std::string((std::istreambuf_iterator<char>(img_file)), std::istreambuf_iterator<char>());

    //start write timer
    std::chrono::time_point<std::chrono::high_resolution_clock> start_w = std::chrono::high_resolution_clock::now();


    for(int i = 0; i < iters; i++){
        //---- time XADD start
        std::string key = "nasa_pic" + std::to_string(i);
        std::chrono::time_point<std::chrono::high_resolution_clock> start_w0 = std::chrono::high_resolution_clock::now();
        
        bredis_con.async_write(xadd_tx_buff, bredis::single_command_t{ "XADD", "bredis", "*", key, img_binary }, [&](const boost::system::error_code &ec, std::size_t bytes_transferred) {
            // tx_buff must be consumed when it is no longer needed
            xadd_tx_buff.consume(bytes_transferred);

            std::chrono::time_point<std::chrono::high_resolution_clock> stop_w0 = std::chrono::high_resolution_clock::now();
            auto dur_w0 = std::chrono::duration_cast<std::chrono::milliseconds>(stop_w0 - start_w0);
            xadd_times.push_back(std::to_string(dur_w0.count()));
        //     time XADD end ---- 


        //---- time XADD read start
            std::chrono::time_point<std::chrono::high_resolution_clock> start_r0 = std::chrono::high_resolution_clock::now();    
            bredis_con.async_read(xadd_rx_buff, [&](const boost::system::error_code &ec, bredis::parse_result_mapper_t<Iterator, Policy> &&result_markers) {
                
                std::chrono::time_point<std::chrono::high_resolution_clock> stop_r0 = std::chrono::high_resolution_clock::now();
                auto dur_r0 = std::chrono::duration_cast<std::chrono::milliseconds>(stop_r0 - start_r0);
                xadd_read_times.push_back(std::to_string(dur_r0.count()));
        //     time XADD read end ---- 

                //---- time XADD extract start
                std::chrono::time_point<std::chrono::high_resolution_clock> start_e0 = std::chrono::high_resolution_clock::now();   
                auto extract = boost::apply_visitor(bredis::extractor<Iterator>(), result_markers.result);
                try{
                    auto &reply_str = boost::get<bredis::extracts::string_t>(extract);
                }catch(boost::bad_get &err){
                        std::cout<<"XADD ERROR @ iter:" << i << ": "<< err.what()<< std::endl;
                        //auto &reply_str = boost::get<bredis::extracts::error_t>(extract); //getting bad boost lexical ast here?
                        //std::cout<<reply_str.str<<std::endl;
                        exit(EXIT_FAILURE);
                }
                std::chrono::time_point<std::chrono::high_resolution_clock> stop_e0 = std::chrono::high_resolution_clock::now();
                auto dur_e0 = std::chrono::duration_cast<std::chrono::milliseconds>(stop_e0 - start_e0);
                xadd_extract_times.push_back(std::to_string(dur_e0.count()));
                //     time XADD extract end ---- 

                // consume the buffers, after finishing work with the markers
                xadd_rx_buff.consume(result_markers.consumed);
            });    
        
        });
    }

    //end write timer
    std::chrono::time_point<std::chrono::high_resolution_clock> stop_w = std::chrono::high_resolution_clock::now();
    auto dur_w = std::chrono::duration_cast<std::chrono::milliseconds>(stop_w - start_w);



    //start read timer
    std::chrono::time_point<std::chrono::high_resolution_clock> start_r = std::chrono::high_resolution_clock::now();

    /* for(int i = 0; i < iters; i++){
        //---- time XRANGE start
        std::string key = "nasa_pic" + std::to_string(i);
        std::chrono::time_point<std::chrono::high_resolution_clock> start_w0 = std::chrono::high_resolution_clock::now();
        
        bredis_con.async_write(xrange_tx_buff, bredis::single_command_t{ "XRANGE" , "bredis",  "-", "+", "COUNT", "10"}, [&](const boost::system::error_code &ec, std::size_t bytes_transferred) {
            // tx_buff must be consumed when it is no longer needed
            xrange_tx_buff.consume(bytes_transferred);

            std::chrono::time_point<std::chrono::high_resolution_clock> stop_w0 = std::chrono::high_resolution_clock::now();
            auto dur_w0 = std::chrono::duration_cast<std::chrono::milliseconds>(stop_w0 - start_w0);
            xrange_times.push_back(std::to_string(dur_w0.count()));
        //     time XRANGE end ---- 


        //---- time XRANGE read start
            std::chrono::time_point<std::chrono::high_resolution_clock> start_r0 = std::chrono::high_resolution_clock::now();    

            bredis_con.async_read(xrange_rx_buff, [&](const boost::system::error_code &ec, bredis::parse_result_mapper_t<Iterator, Policy> &&result_markers) {
                std::chrono::time_point<std::chrono::high_resolution_clock> stop_r0 = std::chrono::high_resolution_clock::now();
                auto dur_r0 = std::chrono::duration_cast<std::chrono::milliseconds>(stop_r0 - start_r0);
                xrange_read_times.push_back(std::to_string(dur_r0.count()));
        //      time XADD read end ---- 

                //---- time XRANGE extract start
                std::chrono::time_point<std::chrono::high_resolution_clock> start_e0 = std::chrono::high_resolution_clock::now();

                auto extract = boost::apply_visitor(bredis::extractor<Iterator>(), result_markers.result);
                try{
                    auto& elems = boost::get<bredis::extracts::array_holder_t>(extract).elements;
                    for(int k = 0; k < 10; k++){
                        try{
                            auto out =  boost::get<bredis::extracts::array_holder_t>(elems[k]);

                            auto id = boost::get<bredis::extracts::string_t>(out.elements[0]);
                            auto payload = boost::get<bredis::extracts::array_holder_t>(out.elements[1]);
                            auto key = boost::get<bredis::extracts::string_t>(payload.elements[0]);
                            auto val = boost::get<bredis::extracts::string_t>(payload.elements[1]);
                            auto byte_arr = val.str.data();

                            //std::cout<<"\nId: "<< id.str << ", key: " << key.str << ", val: "<<std::endl;
                            //for(int j = 0; j < val.str.size(); j++){ 
                            //    std::cout<<std::hex<< "\\" <<(int)byte_arr[j];
                            //} 
                        } catch(boost::bad_get & err){
                            std::cout<<"XRANGE ERROR (in nested get) @ iter:" << i << ": "<< err.what() << std::endl;
                        }
            
                    }
                } catch(boost::bad_get & err){
                        std::cout<<"XRANGE ERROR @ iter:" << i << ": "<< err.what() << std::endl;
                        auto &reply_str = boost::get<bredis::extracts::error_t>(extract);
                        std::cout<<"REDIS REPLY: " << reply_str.str << std::endl;
                }
                std::chrono::time_point<std::chrono::high_resolution_clock> stop_e0 = std::chrono::high_resolution_clock::now();
                auto dur_e0 = std::chrono::duration_cast<std::chrono::milliseconds>(stop_e0 - start_e0);
                xrange_extract_times.push_back(std::to_string(dur_e0.count()));
                //    time XRANGE extract end ---- 

                // consume the buffers, after finishing work with the markers
                xrange_rx_buff.consume(result_markers.consumed);
            });    
        
        });
    } */

    //end read timer
    std::chrono::time_point<std::chrono::high_resolution_clock> stop_r = std::chrono::high_resolution_clock::now();
    auto dur_r = std::chrono::duration_cast<std::chrono::milliseconds>(stop_r - start_r);
    
    //Printout the xadd stats...
    std::cout<<"\n----For Writing----"<<std::endl;
    std::cout<<"Total Elapsed Time for bredis client (" << iters<< "x): "<< dur_w.count()
          << " ms.\n"<< "Average Time for bredis client msg write (XADD): "<< (dur_w/(float)iters).count()
          << " ms"<<std::endl;

    //Printout the xrange stats...
    std::cout<<"----For Reading----"<<std::endl;
    std::cout<<"Total Elapsed Time for bredis client (" << iters<< "x): "<< dur_r.count()
          << " ms.\n"<< "Average Time for bredis client msg read (XRANGE): "<< (dur_r/(float)iters).count()
          << " ms"<<std::endl;


    //Store the timing in the logfile
    for(int i = 0; i < xadd_times.size(); i++){
        bredis_logfile << xadd_times[i] + ", " + xadd_read_times[i] + ", " + xadd_extract_times[i] + ", " 
                        /* + xrange_times[i] + ", " + xrange_read_times[i] + ", " + xrange_extract_times[i] */ +"\n";
    }

    bredis_logfile.close();

    ioserv.run();

}