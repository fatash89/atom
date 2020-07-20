#include <iostream>
#include <chrono>
#include <string>
#include <fstream>
#include <cpp_redis/cpp_redis>
#include <cpp_redis/misc/macro.hpp>
#include <boost/gil.hpp>

void on_connect(const std::string &host, std::size_t port, cpp_redis::connect_state conn_state){
    if (conn_state == cpp_redis::connect_state::dropped){
        std::cout<<"redis client is disconnected."<<std::endl;
    }else if(conn_state == cpp_redis::connect_state::ok){
        std::cout<<"redis client connected @ "<<host<<":"<<port<<std::endl;
    }else{
        std::cout<<"redis client is doing its own thing"<<std::endl;
    }
}

void reply(const cpp_redis::reply &reply){
    //std::cout<< "> " << reply<<std::endl;
}

int main(){
    int iters = 100;

    // log file setup here
    std::ofstream cppredis_logfile;
    cppredis_logfile.open("cpp_redis.log", std::ios_base::app);
    cppredis_logfile << "----- LOGGING AT: " + 
        std::to_string(std::chrono::duration_cast<std::chrono::milliseconds>
            (std::chrono::system_clock::now().time_since_epoch()).count()) + "-----\n";
    
    cppredis_logfile << "xadd (ms), xrange (ms)\n";
    std::vector<std::string> xadd_times;
    std::vector<std::string> xrange_times;

    cpp_redis::client redis_client;

    redis_client.connect("172.20.0.2", 6379, on_connect);

    //init details about cxn
    std::string sname = "cpp_redis";
    std::string gname = "group_name";
    std::string cname = "consumer_name";

    //read image in
    std::ifstream img_file("./clients/data/nasa1.jpg", std::ios::binary);
    std::string img_binary = std::string((std::istreambuf_iterator<char>(img_file)), std::istreambuf_iterator<char>());

    //make dummy data
    std::multimap<std::string, std::string> dat;
    dat.insert(std::pair<std::string, std::string>{"nasa_pic", img_binary});

    //start write timer
    std::chrono::time_point<std::chrono::high_resolution_clock> start_w = std::chrono::high_resolution_clock::now();

    for(int i = 0; i < iters; i++){
        std::chrono::time_point<std::chrono::high_resolution_clock> start_w0 = std::chrono::high_resolution_clock::now();

        //commands only get sent when we call commit
        redis_client.xadd(sname, "*", dat, reply);
        redis_client.sync_commit();
        
        std::chrono::time_point<std::chrono::high_resolution_clock> stop_w0 = std::chrono::high_resolution_clock::now();
        auto dur_w0 = std::chrono::duration_cast<std::chrono::milliseconds>(stop_w0 - start_w0);
        xadd_times.push_back(std::to_string(dur_w0.count()));
    }
    //end write timer
    std::chrono::time_point<std::chrono::high_resolution_clock> stop_w = std::chrono::high_resolution_clock::now();
    auto dur_w = std::chrono::duration_cast<std::chrono::milliseconds>(stop_w - start_w);


    //start read timer
    std::chrono::time_point<std::chrono::high_resolution_clock> start_r = std::chrono::high_resolution_clock::now();

    for(int i = 0; i < iters; i++){
        std::chrono::time_point<std::chrono::high_resolution_clock> start_r0 = std::chrono::high_resolution_clock::now();

        redis_client.xrange(sname, {"-", "+", 10}, reply);
        redis_client.sync_commit();
        
        std::chrono::time_point<std::chrono::high_resolution_clock> stop_r0 = std::chrono::high_resolution_clock::now();
        auto dur_r0 = std::chrono::duration_cast<std::chrono::milliseconds>(stop_r0 - start_r0);
        xrange_times.push_back(std::to_string(dur_r0.count()));
    }

    //end read timer
    std::chrono::time_point<std::chrono::high_resolution_clock> stop_r = std::chrono::high_resolution_clock::now();
    auto dur_r = std::chrono::duration_cast<std::chrono::milliseconds>(stop_r - start_r);

    
    //Printout the stats...
    std::cout<<"----For Writing----"<<std::endl;
    std::cout<<"Total Elapsed Time for cpp_redis client (" << iters<< "x): "<< dur_w.count()
          << " ms.\n"<< "Average Time for cpp_redis client msg write (XADD): "<< (dur_w/(float)iters).count()
          << " ms"<<std::endl;

    //Printout the stats...
    std::cout<<"----For Reading----"<<std::endl;
    std::cout<<"Total Elapsed Time for cpp_redis client (" << iters<< "x): "<< dur_r.count()
          << " ms.\n"<< "Average Time for cpp_redis client msg read (XRANGE): "<< (dur_r/(float)iters).count()
          << " ms"<<std::endl;
            

    //Store the timing in the logfile
    for(int i = 0; i < xrange_times.size(); i++){
        cppredis_logfile << xadd_times[i] + ", " + xrange_times[i] + +"\n";
    }

    cppredis_logfile.close();

    return 0;
}