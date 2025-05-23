from measurements.tools.display_output import *
from measurements.tools.store_output import *
from scipy.stats import weibull_min, gamma, beta
from datetime import datetime as d
import numpy as np
import os
import math
import copy 
import sys

# Global parameters
# PSO parameters                            
iw = 0.9          # Initial Inertia Weight
c1 = 2.0          # Initial Pbest coefficient
c2 = 0.1          # Initial Gbest coefficient
pop_n = 3
max_iter = 20000
velocity_factor = 0.2  # Reduced for finer control

# System parameters
DEPTH = 3
WIDTH = 5
dimensions = sum(WIDTH**i for i in range(DEPTH))
Client_list = []
Role_buffer = []
Role_dictionary = {}
randomness_seed = 11
tracking_mode = False   
distribution_type="normal"

# Experiment parameters
scenario_file_name = f"width_{WIDTH}_{d.now().strftime("%Y-%m-%d_%H:%M:%S")}" 
scenario_folder_number = DEPTH                       
scenario_folder_name = f"depth_{scenario_folder_number}_scenarios"

# Graph illustration required parameters 
file_type = "pdf"
particles_fitness_fig_path = f"./measurements/results/{scenario_folder_name}/particles_fitness_{scenario_file_name}.{file_type}"
swarm_best_fitness_fig_path = f"./measurements/results/{scenario_folder_name}/swarm_best_fitness_{scenario_file_name}.{file_type}"
tpd_fig_path = f"./measurements/results/{scenario_folder_name}/tpd_{scenario_file_name}.{file_type}"
pspeed_fig_path = f"./measurements/results/{scenario_folder_name}/pspeed_{scenario_file_name}.{file_type}"
memcap_fig_path = f"./measurements/results/{scenario_folder_name}/memcap_{scenario_file_name}.{file_type}"

sbpfl = ("iteration" , "best particle fitness")
pfl = ("iteration" , "particles fitness") 
tpdl = ("iteration" , "total processing delay")

# Plot titles, empty for now
sbpft = ""
pft = ""
tpdt = ""

y1 = [] # intertia weight
y2 = [] # c2
y3 = [] # c1

gbest_particle_fitness_results = []
particles_fitnesses_buffer = []
particles_fitnesses_tuples = []

tpd_buffer = []
tpd_tuples = []
iterations = []

pspeed_list = []
memcap_list = []

# CSV output required parameters
csv_particles_output_file_name = f"particles_data_{scenario_file_name}"
csv_swarm_best_output_file_name = f"swarm_best_data_{scenario_file_name}"
csv_tpd_output_file_name = f"tpd_data_{scenario_file_name}"

csv_particles_data_path = f"./measurements/results/{scenario_folder_name}/{csv_particles_output_file_name}.csv"
csv_swarm_best_data_path = f"./measurements/results/{scenario_folder_name}/{csv_swarm_best_output_file_name}.csv"
csv_tpd_data_path = f"./measurements/results/{scenario_folder_name}/{csv_tpd_output_file_name}.csv"

particles_columns = ["iteration"] + [f"particle_{i+1}_fitness" for i in range(pop_n)]
swarm_best_columns = ["iteration", "swarm_best_fitness"]
tpd_columns = ["iteration"] + [f"tpd_particle_{i+1}" for i in range(pop_n)]

csv_cols = [particles_columns, swarm_best_columns, tpd_columns]
csv_rows = [[], [], []]

# JSON output required parameters (Particles constant metadata)
json_path = f"./measurements/results/{scenario_folder_name}/pso_scenario_case_{scenario_file_name}.json"
json_pso_dict = {
    "DEPTH" : DEPTH,
    "WIDTH" : WIDTH,
    "dimensions" : dimensions,
    "randomness_seed" : randomness_seed,
    "iw" : iw,
    "c1" : c1,
    "c2" : c2,
    "pop_n" : pop_n,
    "max_iter" : max_iter,
    "velocity_factor" : velocity_factor,
    "distribution_type" : distribution_type
} 

# Particle class
class Particle :
    def __init__(self, pos , fitness , velocity , best_pos_fitness) : 
        self.pos = pos
        self.fitness = fitness
        self.velocity = velocity
        self.best_pos = self.pos.copy()
        self.best_pos_fitness = best_pos_fitness

# Swarm class
class Swarm : 
    def __init__(self , pop_n , dimensions , root) :
        self.particles = self.__generate_random_particles(pop_n , dimensions , root)
        self.global_best_particle = copy.deepcopy(max(self.particles, key=lambda particle: particle.fitness))

    def __generate_random_particles(self, pop_n, dimensions, root):
        cll = len(Client_list)
        particles = []
        for _ in range(pop_n):
            # Position is now a continuous vector of length client_count
            particle_pos = np.random.rand(cll)
            # Get discrete assignment
            assignment = np.argsort(particle_pos)[:dimensions]
            root = rearrange_hierarchy(assignment)
            fitness, _ = processing_fitness(root)
            velocity = np.zeros(cll)  # Velocity matches position length
            best_pos_fitness = fitness
            particles.append(Particle(particle_pos, fitness, velocity, best_pos_fitness))
        return particles
        
class Client :
    def __init__(self, memcap, mdatasize, client_id , label , pspeed , is_aggregator=False) :
        self.memcap = memcap 
        self.mdatasize = mdatasize
        self.label = label 
        self.pspeed = pspeed
        self.is_aggregator = is_aggregator
        self.client_id = client_id  
        self.processing_buffer = []

    def change_role(self , new_pos) :         # This function traverses the Client_list to find the client with equal client_id then it first buffers the role of the client if the role is trainer, and then associates the new_role_label to the selected client 
        if not self.is_aggregator : 
            Role_buffer.append(self.label) 
        self.processing_buffer = []
        self.label = list(Role_dictionary.keys())[new_pos]
        self.is_aggregator = True
    
    def take_away_role(self) :                 # This function traverses the Client_list and checks for the client that has the selected role in the arguments then it nulls the label and the processing_buffer   
        self.label = None
        self.processing_buffer = []  

# Fitness function
def processing_fitness(master):
    bft_queue = [master]                     # Start with the root node
    levels = []                              # List to store nodes level by level
    total_process_delay = 0

    # Perform BFT to group nodes by levels
    while bft_queue:
        level_size = len(bft_queue)
        current_level = []

        for _ in range(level_size):
            current_node = bft_queue.pop(0)
            current_level.append(current_node)

            if current_node.is_aggregator :
                bft_queue.extend(current_node.processing_buffer)  

        levels.append(current_level)  

    levels.reverse()

    # Calculate delays level by level
    for level in levels:
        cluster_delays = []  

        for node in level:
            if node.is_aggregator :

                # Update the node's mdatasize with its children's cumulative memory size
                cluster_head_memcons = node.mdatasize + sum(
                    child.mdatasize for child in node.processing_buffer
                )
        
                cluster_delay = cluster_head_memcons / node.pspeed
                cluster_delays.append(cluster_delay)

        # Find the maximum cluster delay for the level
        if cluster_delays:
            max_cluster_delay = max(cluster_delays)
            total_process_delay += max_cluster_delay  # Add max delay of the level to the total delay
    
    return -total_process_delay , total_process_delay

def distribute_random_resources(distribution_type, min_val, max_val):
    distribution_type = distribution_type.lower()
    
    if distribution_type == 'uniform':
        value = np.random.uniform(low=min_val, high=max_val)

    elif distribution_type == 'normal':
        mu = (min_val + max_val) / 2
        sigma = (max_val - min_val) / 4
        value = np.random.normal(loc=mu, scale=sigma)

    elif distribution_type == 'lognormal_skew_right':
        log_min = np.log(min_val)
        log_max = np.log(max_val)
        mu = (log_min + log_max) / 2
        sigma = (log_max - log_min) / 4
        value = np.random.lognormal(mean=mu, sigma=sigma)

    elif distribution_type == 'lognormal_skew_left':
        # Use Beta distribution for left skew
        alpha = 5  # Higher alpha pushes values toward max_val
        beta_param = 2  # Lower beta creates a tail toward min_val
        value = beta.rvs(alpha, beta_param)  # Generates value in [0,1]
        value = min_val + (max_val - min_val) * value  # Scale to [min_val, max_val]

    elif distribution_type == 'weibull':
        c = 2
        scale = max_val / (-np.log(0.05)) ** (1/c)
        value = weibull_min.rvs(c=c, scale=scale)

    elif distribution_type == 'gamma':
        a = 4
        mean = (min_val + max_val) / 2
        scale = mean / a
        value = gamma.rvs(a=a, scale=scale)

    else:
        value = np.random.randint(min_val, max_val)
    
    value = np.clip(value, min_val, max_val)
    return value

def generate_hierarchy(depth, width):
    level_agtrainer_list = []
    agtrainer_list = []
    trainer_list = []

    def create_agtrainer(label_prefix, level):
        pspeed = distribute_random_resources(distribution_type, 2, 8)
        memcap = distribute_random_resources(distribution_type, 10, 50)
        mdatasize = 5                         # in the beginning it's a fixed value but in the future as a stretch goal we can have variable MDataSize due to quantization and knowledge distillation techniques
        length = len(Client_list) 
        new_client = Client(memcap, mdatasize, length, f"t{label_prefix}ag{level}", pspeed, True)
        Client_list.append(new_client)
        agtrainer_list.append(new_client)
        pspeed_list.append(pspeed)
        memcap_list.append(memcap)
        level_agtrainer_list.append(new_client)
        return new_client

    def create_trainer(label_prefix):
        pspeed = distribute_random_resources(distribution_type, 2, 8)
        memcap = distribute_random_resources(distribution_type, 10, 50)
        mdatasize = 5 
        length = len(Client_list)
        new_client = Client(memcap, mdatasize, length, label_prefix , pspeed)
        pspeed_list.append(pspeed)
        memcap_list.append(memcap)
        Client_list.append(new_client)
        trainer_list.append(new_client)
        return new_client

    root = create_agtrainer(0, 0)
    current_level = [root]
    level_agtrainer_list = []

    for d in range(1, depth):
        next_level = []
        for parent in current_level:
            for _ in range(width):
                child = create_agtrainer(len(level_agtrainer_list), d)
                parent.processing_buffer.append(child)
                next_level.append(child)

                for role in [parent , child] :
                    Role_dictionary[role.label] = [child.label for child in role.processing_buffer]

        if d == depth - 1:    
            for client in level_agtrainer_list :
                for j in range(2):          
                    trainer = create_trainer(f"{client.label}_{j+1}")
                    client.processing_buffer.append(trainer)

                for role in [client , trainer] :
                    Role_dictionary[role.label] = [child.label for child in role.processing_buffer]

        level_agtrainer_list = []
        current_level = next_level

    return root

def print_hierarchy(node, level=0, is_last=True, prefix=""):
    connector = "└── " if is_last else "├── "
    if node.is_aggregator : 
        print(f"{prefix}{connector}{node.label} (MemCap: {node.memcap}, MDataSize: {node.mdatasize} Pspeed: {node.pspeed}, ID: {node.client_id})")

    elif node.is_aggregator == False :
        print(f"{prefix}{connector}{node.label} (MemCap: {node.memcap}, MDataSize: {node.mdatasize}, ID: {node.client_id})")

    if node.is_aggregator :
        for i, child in enumerate(node.processing_buffer):
            new_prefix = prefix + ("    " if is_last else "│   ")
            print_hierarchy(child, level + 1, i == len(node.processing_buffer) - 1, new_prefix) 


def rearrange_hierarchy(pso_particle) :            # This function has the iterative approach to perform change role and take away role
    for new_pos , clid in enumerate(pso_particle) : 
        for client in Client_list : 
            if client.label == list(Role_dictionary.keys())[new_pos] :
                client.take_away_role()

            if client.client_id == clid : 
                client.change_role(new_pos)
                
    for client in Client_list : 
        if client.label == None :
            client.label = Role_buffer.pop()    
            client.is_aggregator = False 
    
        if client.is_aggregator : 
            if len(client.processing_buffer) == 0 : 
                temp = Role_dictionary[client.label]
                for role in temp : 
                    for c in Client_list :
                        if c.label == role : 
                            client.processing_buffer.append(c) 
                        
    for client in Client_list :
        if client.label == list(Role_dictionary.keys())[0] :
            return client

def update_velocity(current_velocity, current_position, personal_best, global_best, iw, c1, c2):
    r1 = np.random.rand(len(current_velocity))
    r2 = np.random.rand(len(current_velocity))
    
    inertia = iw * current_velocity
    cognitive = c1 * r1 * (personal_best - current_position)
    social = c2 * r2 * (global_best - current_position)
    
    new_velocity = inertia + cognitive + social
    max_velocity = max(1.0, len(current_velocity) * velocity_factor)  # Adjust as float
    new_velocity = np.clip(new_velocity, -max_velocity, max_velocity)
    
    return new_velocity

def apply_velocity(p_position, p_velocity):
    new_position = p_position + p_velocity
    # Clip to [0,1] to keep values bounded
    new_position = np.clip(new_position, 0, 1)
    return new_position


def growth_rate(k, t0, counter):
    # k = 0.3    # Growth steepness
    # t0 = 0     # Counter value where growth_rate = 0.55
    P = 1 / (1 + math.exp(-k * (counter - t0)))
    return P

def pso_fl_sim() :    
    global iw, c1, c2, velocity_factor

    if tracking_mode : 
        np.random.seed(randomness_seed)

    root = generate_hierarchy(DEPTH , WIDTH)
    initial_root = copy.deepcopy(root)
    _ , initial_tpd = processing_fitness(root)
    
    # This line adds initial hierarchy TPD to the plot
    # tpd_tuples.append([initial_tpd] * pop_n)

    counter = 1

    swarm = Swarm(pop_n , dimensions , root)

    while counter <= max_iter:
        for particle in swarm.particles:
            particles_fitnesses_buffer.append(particle.fitness)
            
            new_velocity = update_velocity(particle.velocity, particle.pos, particle.best_pos, swarm.global_best_particle.best_pos, iw, c1, c2)
            new_position = apply_velocity(particle.pos, new_velocity)
            assignment = np.argsort(new_position)[:dimensions]
            
            root = rearrange_hierarchy(assignment)
            new_pos_fitness, tpd = processing_fitness(root)
            
            particle.pos = new_position
            particle.fitness = new_pos_fitness
            particle.velocity = new_velocity
            
            if particle.fitness > particle.best_pos_fitness:
                particle.best_pos = particle.pos.copy()
                particle.best_pos_fitness = copy.copy(particle.fitness)

            if particle.fitness > swarm.global_best_particle.fitness:
                swarm.global_best_particle = copy.deepcopy(particle)           
            
            tpd_buffer.append(tpd)

        iw = 0.9 - 0.3 * (counter / max_iter)  # From 0.9 to 0.4
        c1 = 0.5 - 0.5 * (counter / max_iter)  # From 2.0 to 0.5
        c2 = 0.3 + 0.7 * (counter / max_iter)  # From 0.5 to 2.0

        iterations.append(counter)
        
        gbest_particle_fitness_results.append(swarm.global_best_particle.fitness)
        tpd_tuples.append(tpd_buffer.copy())
        particles_fitnesses_tuples.append(particles_fitnesses_buffer.copy()) # We could simply reverse the TPD plot and get Particles Fitnesses Plot but as the fitness function might change later this method is not reliable 
        
        particles_row = [counter] + [round(fitness , 2) for fitness in particles_fitnesses_buffer]
        csv_rows[0].append(particles_row)
        
        swarm_best_row = [counter, round(swarm.global_best_particle.fitness , 2)]
        csv_rows[1].append(swarm_best_row)
        
        tpd_row = [counter] + [round(tpd , 2) for tpd in tpd_buffer]
        csv_rows[2].append(tpd_row)

        os.system("cls") if sys.platform == "win32" else os.system("clear")
        print("iw : ", iw)
        print("c2 : ", c2)
        print("c1 : ", c1)
        print("dimensions : ", dimensions)
        print(f"Iteration : {counter}") 
        
        tpd_buffer.clear()
        particles_fitnesses_buffer.clear()
        
        counter += 1

    print_hierarchy(initial_root)
    print("Dimensions : " , dimensions)
    print(f"Initial TPD Before PSO : {initial_tpd}")
    print(f"Final Best TPD After PSO : {-swarm.global_best_particle.fitness}\n")

    save_data_to_csv(csv_cols[0] , csv_rows[0] , csv_particles_data_path)
    save_data_to_csv(csv_cols[1] , csv_rows[1] , csv_swarm_best_data_path)
    save_data_to_csv(csv_cols[2] , csv_rows[2] , csv_tpd_data_path)
    save_metadata_to_json(json_pso_dict , json_path)

    histogram_plot(pspeed_list, pspeed_fig_path)
    histogram_plot(memcap_list, memcap_fig_path)

    show_plot(gbest_particle_fitness_results , sbpfl , sbpft , swarm_best_fitness_fig_path)
    
    plot_tuple_curves(particles_fitnesses_tuples , pfl , pft , particles_fitness_fig_path)
    plot_tuple_curves(tpd_tuples , tpdl , tpdt , tpd_fig_path)
    

if __name__ == "__main__" : 
    pso_fl_sim()


#iw = 1.1 - growth_rate(0.1, max_iter // 3, counter)
# y1.append(iw)

#c1 = 1.1 - growth_rate(0.05, max_iter // 3, counter)
# y3.append(c1)

#c2 = growth_rate(0.05, max_iter // 3, counter)